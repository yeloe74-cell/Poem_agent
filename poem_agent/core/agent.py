class Agent:
    """Extensible asynchronous Agent Core.

    Expected adapter contracts:

    brain.process(message=..., context=..., tools=...)
        Returns str, AgentResult or a mapping.

    memory.build_context(owner_id)
        Returns optional context text.

    memory.add_turn(owner_id, role, content)
        Stores a conversation turn.

    messenger.send_message(owner_id, text)
        Sends a message to the owner.

    Tool handlers receive:
        handler(context=AgentContext, arguments=dict)

    Tool handlers should preferably be asynchronous.
    """

    def __init__(
        self,
        *,
        brain: Any = None,
        memory: Any = None,
        database: Any = None,
        messenger: Any = None,
        permission_guard: Any = None,
        config: AgentConfig | None = None,
    ) -> None:
        self.config = config or AgentConfig()

        self.brain = brain
        self.memory = memory
        self.database = database
        self.messenger = messenger
        self.permission_guard = permission_guard

        self.state = AgentState.CREATED

        self.events = EventBus()
        self.tools = ToolRegistry()

        self.approvals = ApprovalManager(
            timeout=self.config.approval_timeout
        )

        self.extensions = ExtensionManager(
            self,
            api_version=self.config.core_api_version,
        )

        self._middleware: list[Middleware] = []

        self._lifecycle_lock = asyncio.Lock()
        self._owner_locks: dict[str, asyncio.Lock] = {}

        self._tool_semaphore = asyncio.Semaphore(
            self.config.max_concurrent_tool_calls
        )

        self._background_tasks: dict[
            str,
            asyncio.Task[Any],
        ] = {}

        self._started_at: float | None = None
        self._shutdown_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self.state == AgentState.RUNNING

    def add_middleware(self, middleware: Middleware) -> None:
        if middleware in self._middleware:
            raise ValueError("Middleware already registered")

        self._middleware.append(middleware)

    def remove_middleware(self, middleware: Middleware) -> bool:
        if middleware not in self._middleware:
            return False

        self._middleware.remove(middleware)
        return True

    def register_tool(self, spec: ToolSpec) -> None:
        self.tools.register(spec)

    def register_extension(self, extension: Extension) -> None:
        self.extensions.register(extension)

    def subscribe(
        self,
        event_name: str,
        callback: Callable[..., Any],
    ) -> None:
        self.events.subscribe(event_name, callback)

    async def startup(self) -> None:
        async with self._lifecycle_lock:
            if self.state == AgentState.RUNNING:
                return

            if self.state in (
                AgentState.STARTING,
                AgentState.STOPPING,
            ):
                raise AgentNotReadyError(
                    f"Cannot start while state is {self.state.value}"
                )

            self.state = AgentState.STARTING
            self._shutdown_event.clear()

            try:
                await self.extensions.start_all()

                self._started_at = time.monotonic()
                self.state = AgentState.RUNNING

                await self.events.emit("agent.started")

                logger.info("Agent started successfully")

            except Exception:
                self.state = AgentState.FAILED

                logger.exception("Agent startup failed")

                raise

    async def shutdown(self) -> None:
        async with self._lifecycle_lock:
            if self.state == AgentState.STOPPED:
                return

            self.state = AgentState.STOPPING

            await self.events.emit("agent.stopping")

            self._shutdown_event.set()

            await self.cancel_all_tasks()

            try:
                await self.extensions.stop_all()

            except Exception:
                logger.exception("Extension shutdown failed")

            await self.approvals.clear()

            self._owner_locks.clear()

            self.state = AgentState.STOPPED

            await self.events.emit("agent.stopped")

            logger.info("Agent stopped")

    def _get_owner_lock(self, owner_id: str) -> asyncio.Lock:
        lock = self._owner_locks.get(owner_id)

        if lock is None:
            lock = asyncio.Lock()
            self._owner_locks[owner_id] = lock

        return lock

    async def handle_message(
        self,
        owner_id: str,
        message: str,
    ) -> AgentResult:
        """Main entry point for incoming owner messages.

        owner_id must come from a trusted, authenticated
        Telegram or application identity.
        """

        if not self.is_running:
            raise AgentNotReadyError("Agent is not running")

        if not owner_id or not isinstance(owner_id, str):
            raise ValueError("A valid owner_id is required")

        if not isinstance(message, str):
            raise TypeError("Message must be a string")

        message = message.strip()

        if not message:
            return AgentResult(
                success=False,
                content="Message cannot be empty.",
            )

        if len(message) > self.config.max_message_length:
            return AgentResult(
                success=False,
                content="Message is too long.",
            )

        lock = self._get_owner_lock(owner_id)

        async with lock:
            context = AgentContext(
                owner_id=owner_id,
                user_message=message,
                max_tool_calls=self.config.max_tool_calls_per_request,
            )

            await self.events.emit(
                "message.received",
                context=context,
            )

            try:
                pending = await self.approvals.get(owner_id)

                if pending is not None:
                    result = await self._handle_pending_approval(
                        context,
                        message,
                        pending,
                    )
                else:
                    result = await self._process_message(context)

                await self._store_turn(
                    owner_id,
                    "user",
                    message,
                )

                if result.content:
                    await self._store_turn(
                        owner_id,
                        "assistant",
                        result.content,
                    )

                await self.events.emit(
                    "message.completed",
                    context=context,
                    result=result,
                )

                return result

            except Exception as exc:
                logger.exception(
                    "Message processing failed for request %s",
                    context.request_id,
                )

                await self.events.emit(
                    "message.failed",
                    context=context,
                    error=str(exc),
                )

                await self._log_error(
                    "message_processing",
                    exc,
                    context,
                )

                return AgentResult(
                    success=False,
                    request_id=context.request_id,
                    error=str(exc),
                    content="An error occurred while processing your request.",
                )

            finally:
                self._owner_locks.pop(owner_id, None)

    async def _process_message(
        self,
        context: AgentContext,
    ) -> AgentResult:
        if self.brain is None:
            return AgentResult(
                success=False,
                request_id=context.request_id,
                content="AI Brain is not configured.",
                error="Missing brain adapter",
            )

        try:
            context.memory_context = await self._build_memory_context(
                context.owner_id
            )

            for middleware in self._middleware:
                outcome = await invoke(
                    middleware.before,
                    context,
                )

                if outcome is False:
                    return AgentResult(
                        success=False,
                        request_id=context.request_id,
                        content="This request was blocked by middleware.",
                    )

            response = await invoke(
                self.brain.process,
                message=context.user_message,
                context=context,
                tools=self.tools.list_tools(),
            )

            result = await self._normalize_brain_response(
                response,
                context,
            )

            for middleware in reversed(self._middleware):
                updated = await invoke(
                    middleware.after,
                    context,
                    result,
                )

                if isinstance(updated, AgentResult):
                    result = updated

            return result

        except Exception as exc:
            logger.exception("Brain processing failed")

            return AgentResult(
                success=False,
                request_id=context.request_id,
                error=str(exc),
                content="I couldn't complete that request.",
            )

    async def _normalize_brain_response(
        self,
        response: Any,
        context: AgentContext,
    ) -> AgentResult:
        if isinstance(response, AgentResult):
            response.request_id = context.request_id
            return response

        if isinstance(response, str):
            return AgentResult(
                success=True,
                request_id=context.request_id,
                content=response,
            )

        if isinstance(response, Mapping):
            tool_calls = response.get("tool_calls")

            if tool_calls:
                return await self._execute_brain_tool_calls(
                    tool_calls,
                    context,
                )

            return AgentResult(
                success=bool(response.get("success", True)),
                request_id=context.request_id,
                content=str(response.get("content", "")),
                error=response.get("error"),
                data=response.get("data"),
                metadata=dict(response.get("metadata", {})),
            )

        return AgentResult(
            success=False,
            request_id=context.request_id,
            content="AI Brain returned an unsupported response.",
            error="Invalid brain response type",
        )

    async def _execute_brain_tool_calls(
        self,
        tool_calls: Any,
        context: AgentContext,
    ) -> AgentResult:
        if not isinstance(tool_calls, (list, tuple)):
            raise ToolExecutionError(
                "tool_calls must be a list"
            )

        outputs: list[dict[str, Any]] = []

        for item in tool_calls:
            if not isinstance(item, Mapping):
                raise ToolExecutionError(
                    "Invalid tool call format"
                )

            name = str(item.get("name", "")).strip()

            arguments = item.get("arguments", {})

            if not isinstance(arguments, Mapping):
                raise ToolExecutionError(
                    "Tool arguments must be an object"
                )

            result = await self.execute_tool(
                context=context,
                name=name,
                arguments=arguments,
            )

            outputs.append({
                "tool": name,
                "success": result.success,
                "content": result.content,
                "data": result.data,
                "error": result.error,
            })

            if result.metadata.get("approval_required"):
                return result

            if not result.success:
                return result

        return AgentResult(
            success=True,
            request_id=context.request_id,
            content="Tool execution completed.",
            data={"tool_results": outputs},
        )

    async def execute_tool(
        self,
        *,
        context: AgentContext,
        name: str,
        arguments: Mapping[str, Any],
        approved: bool = False,
    ) -> AgentResult:
        if not self.is_running:
            raise AgentNotReadyError("Agent is not running")

        tool = self.tools.get(name)

        if not isinstance(arguments, Mapping):
            raise ToolExecutionError(
                "Tool arguments must be a mapping"
            )

        safe_arguments = dict(arguments)

        try:
            await self._check_permission(
                context,
                tool,
                safe_arguments,
                approved=approved,
            )

            if tool.validator is not None:
                valid = await invoke(
                    tool.validator,
                    safe_arguments,
                )

                if valid is False:
                    raise ToolExecutionError(
                        "Tool argument validation failed"
                    )

            needs_approval = self._requires_approval(tool)

            if needs_approval and not approved:
                pending = await self.approvals.create(
                    owner_id=context.owner_id,
                    tool_name=tool.name,
                    arguments=safe_arguments,
                )

                await self.events.emit(
                    "approval.required",
                    context=context,
                    approval=pending,
                )

                return AgentResult(
                    success=True,
                    request_id=context.request_id,
                    content=(
                        f"ဒီလုပ်ဆောင်ချက်ကို အတည်ပြုပေးပါ။\n"
                        f"Tool: {tool.name}\n"
                        f"Action ID: {pending.action_id}\n"
                        f"အတည်ပြုရန် 'အတည်ပြု' ဟု ပြောပါ။\n"
                        f"ပယ်ဖျက်ရန် 'မလုပ်နဲ့' ဟု ပြောပါ။"
                    ),
                    metadata={
                        "approval_required": True,
                        "action_id": pending.action_id,
                    },
                )

            return await self._run_tool(
                context,
                tool,
                safe_arguments,
                approved=approved,
            )

        except Exception as exc:
            logger.exception("Tool execution failed: %s", name)

            await self.events.emit(
                "tool.failed",
                context=context,
                tool_name=name,
                error=str(exc),
            )

            await self._log_error(
                f"tool:{name}",
                exc,
                context,
            )

            return AgentResult(
                success=False,
                request_id=context.request_id,
                error=str(exc),
                content=f"Tool execution failed: {name}",
            )

    def _requires_approval(self, tool: ToolSpec) -> bool:
        if tool.requires_approval:
            return True

        if (
            tool.risk == RiskLevel.HIGH
            and self.config.require_approval_for_high_risk
        ):
            return True

        if (
            tool.risk == RiskLevel.CRITICAL
            and self.config.require_approval_for_critical
        ):
            return True

        return False

    async def _check_permission(
        self,
        context: AgentContext,
        tool: ToolSpec,
        arguments: Mapping[str, Any],
        *,
        approved: bool,
    ) -> None:
        guard = self.permission_guard

        if guard is None:
            return

        checker = getattr(guard, "check", None)

        if checker is None:
            if not callable(guard):
                raise PermissionError(
                    "Invalid permission guard"
                )

            checker = guard

        allowed = await invoke(
            checker,
            context=context,
            tool=tool,
            arguments=arguments,
            approved=approved,
        )

        if allowed is not True:
            raise PermissionError(
                f"Permission denied for tool: {tool.name}"
            )

    async def _run_tool(
        self,
        context: AgentContext,
        tool: ToolSpec,
        arguments: Mapping[str, Any],
        *,
        approved: bool,
    ) -> AgentResult:
        context.consume_tool_call()

        timeout = tool.timeout or self.config.default_tool_timeout

        await self.events.emit(
            "tool.started",
            context=context,
            tool_name=tool.name,
        )

        async with self._tool_semaphore:
            try:
                async def call_handler() -> Any:
                    if inspect.iscoroutinefunction(tool.handler):
                        return await tool.handler(
                            context=context,
                            arguments=dict(arguments),
                        )

                    result = await asyncio.to_thread(
                        tool.handler,
                        context=context,
                        arguments=dict(arguments),
                    )

                    if inspect.isawaitable(result):
                        return await result

                    return result

                output = await asyncio.wait_for(
                    call_handler(),
                    timeout=timeout,
                )

                await self.events.emit(
                    "tool.completed",
                    context=context,
                    tool_name=tool.name,
                    output=output,
                )

                await self._log_tool(
                    context,
                    tool.name,
                    "completed",
                )

                return AgentResult(
                    success=True,
                    request_id=context.request_id,
                    content=f"Tool completed: {tool.name}",
                    data=output,
                    metadata={
                        "tool_name": tool.name,
                        "approved": approved,
                    },
                )

            except asyncio.TimeoutError as exc:
                raise ToolExecutionError(
                    f"Tool timed out: {tool.name}"
                ) from exc

            except Exception as exc:
                raise ToolExecutionError(
                    f"{tool.name}: {exc}"
                ) from exc

    async def _handle_pending_approval(
        self,
        context: AgentContext,
        message: str,
        pending: PendingApproval,
    ) -> AgentResult:
        normalized = message.strip().lower()

        confirm_words = {
            "အတည်ပြု",
            "အတည်ပြုပါ",
            "လုပ်လိုက်",
            "လုပ်ပါ",
            "yes",
            "confirm",
            "approve",
            "တင်လိုက်",
        }

        cancel_words = {
            "မလုပ်နဲ့",
            "ပယ်ဖျက်",
            "ဖျက်လိုက်",
            "မလုပ်တော့ဘူး",
            "no",
            "cancel",
            "reject",
            "deny",
        }

        if normalized in cancel_words:
            await self.approvals.cancel(context.owner_id)

            await self.events.emit(
                "approval.cancelled",
                context=context,
                approval=pending,
            )

            return AgentResult(
                success=True,
                request_id=context.request_id,
                content="လုပ်ဆောင်ချက်ကို ပယ်ဖျက်လိုက်ပါပြီ။",
            )

        if normalized not in confirm_words:
            return AgentResult(
                success=True,
                request_id=context.request_id,
                content=(
                    "အတည်ပြုရန် 'အတည်ပြု'၊ "
                    "ပယ်ဖျက်ရန် 'မလုပ်နဲ့' ဟု ပြောပေးပါ။"
                ),
                metadata={
                    "approval_required": True,
                    "action_id": pending.action_id,
                },
            )

        try:
            approval = await self.approvals.consume(
                context.owner_id,
                pending.action_id,
            )

            tool = self.tools.get(approval.tool_name)

            await self.events.emit(
                "approval.accepted",
                context=context,
                approval=approval,
            )

            result = await self._run_approved_tool(
                context,
                tool,
                approval.arguments,
            )

            return result

        except Exception as exc:
            logger.exception("Approval execution failed")

            return AgentResult(
                success=False,
                request_id=context.request_id,
                content="အတည်ပြုပြီးနောက် လုပ်ဆောင်မှု မအောင်မြင်ပါ။",
                error=str(exc),
            )

    async def _run_approved_tool(
        self,
        context: AgentContext,
        tool: ToolSpec,
        arguments: Mapping[str, Any],
    ) -> AgentResult:
        try:
            await self._check_permission(
                context,
                tool,
                arguments,
                approved=True,
            )

            if tool.validator is not None:
                valid = await invoke(
                    tool.validator,
                    arguments,
                )

                if valid is False:
                    raise ToolExecutionError(
                        "Approved arguments failed validation"
                    )

            return await self._run_tool(
                context,
                tool,
                arguments,
                approved=True,
            )

        except Exception as exc:
            logger.exception(
                "Approved tool execution failed: %s",
                tool.name,
            )

            return AgentResult(
                success=False,
                request_id=context.request_id,
                content="အတည်ပြုထားသော လုပ်ဆောင်ချက် မအောင်မြင်ပါ။",
                error=str(exc),
            )

    async def _build_memory_context(
        self,
        owner_id: str,
    ) -> str:
        if self.memory is None:
            return ""

        builder = getattr(
            self.memory,
            "build_context",
            None,
        )

        if builder is None:
            return ""

        result = await invoke(
            builder,
            owner_id,
        )

        return str(result or "")

    async def _store_turn(
        self,
        owner_id: str,
        role: str,
        content: str,
    ) -> None:
        if self.memory is None:
            return

        add_turn = getattr(
            self.memory,
            "add_turn",
            None,
        )

        if add_turn is None:
            return

        try:
            await invoke(
                add_turn,
                owner_id,
                role,
                content,
            )

        except Exception:
            logger.exception("Memory storage failed")

    async def _log_tool(
        self,
        context: AgentContext,
        tool_name: str,
        status: str,
    ) -> None:
        if self.database is None:
            return

        callback = getattr(
            self.database,
            "log_tool_execution",
            None,
        )

        if callback is None:
            return

        try:
            await invoke(
                callback,
                request_id=context.request_id,
                owner_id=context.owner_id,
                tool_name=tool_name,
                status=status,
            )

        except Exception:
            logger.exception("Tool audit logging failed")

    async def _log_error(
        self,
        source: str,
        error: Exception,
        context: AgentContext,
    ) -> None:
        if self.database is None:
            return

        callback = getattr(
            self.database,
            "log_error",
            None,
        )

        if callback is None:
            return

        try:
            await invoke(
                callback,
                source=source,
                error=str(error),
                request_id=context.request_id,
                owner_id=context.owner_id,
            )

        except Exception:
            logger.exception("Error logging failed")

    def create_background_task(
        self,
        coroutine: Awaitable[Any],
        *,
        name: str | None = None,
    ) -> str:
        if not self.is_running:
            raise AgentNotReadyError(
                "Cannot create tasks while Agent is not running"
            )

        task_id = new_id("task_")
        task_name = name or task_id

        task = asyncio.create_task(
            coroutine,
            name=task_name,
        )

        self._background_tasks[task_id] = task

        def on_done(
            completed: asyncio.Task[Any],
            identifier: str = task_id,
        ) -> None:
            self._background_tasks.pop(identifier, None)

            if completed.cancelled():
                logger.info(
                    "Background task cancelled: %s",
                    identifier,
                )
                return

            error = completed.exception()

            if error is not None:
                logger.error(
                    "Background task failed: %s",
                    identifier,
                    exc_info=(
                        type(error),
                        error,
                        error.__traceback__,
                    ),
                )

        task.add_done_callback(on_done)

        return task_id

    async def cancel_task(self, task_id: str) -> bool:
        task = self._background_tasks.get(task_id)

        if task is None:
            return False

        task.cancel()

        try:
            await task

        except asyncio.CancelledError:
            pass

        return True

    async def cancel_all_tasks(self) -> None:
        tasks = list(self._background_tasks.values())

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        self._background_tasks.clear()

    async def send_owner_message(
        self,
        owner_id: str,
        message: str,
    ) -> bool:
        if self.messenger is None:
            return False

        sender = getattr(
            self.messenger,
            "send_message",
            None,
        )

        if sender is None:
            return False

        await invoke(
            sender,
            owner_id,
            message,
        )

        return True

    async def health(self) -> dict[str, Any]:
        pending_count = await self.approvals.count()

        return {
            "state": self.state.value,
            "api_version": self.config.core_api_version,
            "uptime_seconds": (
                round(time.monotonic() - self._started_at, 2)
                if self._started_at is not None
                else 0
            ),
            "tools": self.tools.count(),
            "extensions": self.extensions.list_extensions(),
            "extension_count": self.extensions.count(),
            "pending_approvals": pending_count,
            "background_tasks": len(self._background_tasks),
            "event_listeners": self.events.listener_count(),
            "middleware_count": len(self._middleware),
        }

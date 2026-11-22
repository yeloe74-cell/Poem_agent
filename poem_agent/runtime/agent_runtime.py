
from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from runtime.event_bus import AgentEvent, EventBus


logger = logging.getLogger(__name__)


class RuntimeErrorBase(Exception):
    """Base exception for runtime operations."""


class RuntimeBudgetExceeded(RuntimeErrorBase):
    """Raised when a runtime execution budget is exceeded."""


class RuntimeClosedError(RuntimeErrorBase):
    """Raised when the runtime is no longer accepting work."""


class RuntimeStepError(RuntimeErrorBase):
    """Raised when a runtime step fails."""


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    """Hard limits for one runtime execution."""

    max_steps: int = 8
    max_wall_seconds: float = 90.0
    max_tool_calls: int = 12
    max_output_chars: int = 12000

    max_step_seconds: float = 30.0
    max_concurrent_runs: int = 4

    def normalized(self) -> RuntimeLimits:
        return RuntimeLimits(
            max_steps=max(
                1,
                min(int(self.max_steps), 30),
            ),
            max_wall_seconds=max(
                1.0,
                min(float(self.max_wall_seconds), 600.0),
            ),
            max_tool_calls=max(
                1,
                min(int(self.max_tool_calls), 60),
            ),
            max_output_chars=max(
                500,
                min(int(self.max_output_chars), 50000),
            ),
            max_step_seconds=max(
                0.5,
                min(float(self.max_step_seconds), 180.0),
            ),
            max_concurrent_runs=max(
                1,
                min(int(self.max_concurrent_runs), 32),
            ),
        )


@dataclass(slots=True)
class RuntimeTrace:
    """Execution trace for one runtime session."""

    run_id: str = field(
        default_factory=lambda: uuid.uuid4().hex
    )

    started_at: float = field(
        default_factory=time.monotonic
    )

    finished_at: float | None = None

    steps: list[dict[str, Any]] = field(
        default_factory=list
    )

    tool_calls: int = 0

    status: str = "running"

    error: str | None = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.finished_at or time.monotonic()

        return max(
            0.0,
            end - self.started_at,
        )

    def finish(self, status: str) -> None:
        self.status = status
        self.finished_at = time.monotonic()


@dataclass(frozen=True, slots=True)
class RuntimeStep:
    """A named trusted callback."""

    callback: Callable[[], Any]

    name: str = "step"

    timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if not callable(self.callback):
            raise TypeError(
                "RuntimeStep callback must be callable"
            )

        if not self.name or len(self.name) > 100:
            raise ValueError(
                "RuntimeStep name must contain 1-100 characters"
            )

        if (
            self.timeout_seconds is not None
            and self.timeout_seconds <= 0
        ):
            raise ValueError(
                "timeout_seconds must be positive"
            )


class AgentRuntime:
    """Bounded asynchronous execution engine.

    Responsibilities:
    - Execute trusted callbacks in a controlled sequence.
    - Enforce step and time budgets.
    - Support cancellation.
    - Record execution traces.
    - Publish lifecycle events.
    - Isolate ordinary step failures.

    Planning and tool authorization remain separate.
    Model-generated code is never executed.
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        limits: RuntimeLimits | None = None,
    ) -> None:
        self.events = event_bus or EventBus()

        self.limits = (
            limits or RuntimeLimits()
        ).normalized()

        self._semaphore = asyncio.Semaphore(
            self.limits.max_concurrent_runs
        )

        self._active_runs: dict[str, RuntimeTrace] = {}

        self._closed = False

        self._lock = asyncio.Lock()

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def active_runs(self) -> int:
        return len(self._active_runs)

    async def run(
        self,
        steps: list[Callable[[], Any] | RuntimeStep],
        *,
        context: Mapping[str, Any] | None = None,
        stop: asyncio.Event | None = None,
    ) -> dict[str, Any]:
        """Execute a sequence of trusted steps."""

        if self._closed:
            raise RuntimeClosedError(
                "Runtime is closed"
            )

        if not isinstance(steps, list):
            raise TypeError(
                "steps must be a list"
            )

        if len(steps) > self.limits.max_steps:
            raise RuntimeBudgetExceeded(
                "Runtime step budget exceeded"
            )

        normalized_steps = self._normalize_steps(
            steps
        )

        async with self._semaphore:
            if self._closed:
                raise RuntimeClosedError(
                    "Runtime is closed"
                )

            return await self._execute(
                normalized_steps,
                context=context,
                stop=stop,
            )

    def _normalize_steps(
        self,
        steps: list[Callable[[], Any] | RuntimeStep],
    ) -> list[RuntimeStep]:
        """Convert callbacks into validated RuntimeStep objects."""

        result: list[RuntimeStep] = []

        for index, item in enumerate(steps, start=1):
            if isinstance(item, RuntimeStep):
                result.append(item)

            elif callable(item):
                result.append(
                    RuntimeStep(
                        callback=item,
                        name=f"step_{index}",
                    )
                )

            else:
                raise TypeError(
                    f"Invalid runtime step at index {index}"
                )

        return result

    async def _execute(
        self,
        steps: list[RuntimeStep],
        *,
        context: Mapping[str, Any] | None,
        stop: asyncio.Event | None,
    ) -> dict[str, Any]:
        trace = RuntimeTrace()

        async with self._lock:
            self._active_runs[trace.run_id] = trace

        safe_context = self._safe_context(context)

        try:
            await self._publish(
                "runtime.started",
                {
                    "run_id": trace.run_id,
                    "context_keys": list(
                        safe_context.keys()
                    )[:30],
                },
                correlation_id=trace.run_id,
            )

            deadline = (
                time.monotonic()
                + self.limits.max_wall_seconds
            )

            for index, step in enumerate(
                steps,
                start=1,
            ):
                if self._closed:
                    trace.finish("cancelled")
                    break

                if stop is not None and stop.is_set():
                    trace.finish("cancelled")
                    break

                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    trace.finish("timeout")
                    break

                if (
                    trace.tool_calls
                    >= self.limits.max_tool_calls
                ):
                    trace.finish("budget_exhausted")
                    break

                result = await self._execute_step(
                    trace,
                    step,
                    index,
                    remaining,
                    stop,
                )

                if result == "failed":
                    trace.finish("failed")
                    break

                if result == "cancelled":
                    trace.finish("cancelled")
                    break

                if result == "timeout":
                    trace.finish("timeout")
                    break

            else:
                trace.finish("completed")

            if trace.status == "running":
                trace.finish("completed")

        except asyncio.CancelledError:
            trace.finish("cancelled")
            raise

        except Exception as exc:
            trace.error = (
                f"{type(exc).__name__}: {str(exc)[:300]}"
            )

            trace.finish("failed")

            logger.exception(
                "Runtime execution failed: %s",
                trace.run_id,
            )

        finally:
            if trace.finished_at is None:
                trace.finish("failed")

            await self._publish(
                "runtime.finished",
                {
                    "run_id": trace.run_id,
                    "status": trace.status,
                    "steps": len(trace.steps),
                    "tool_calls": trace.tool_calls,
                    "elapsed_ms": int(
                        trace.elapsed_seconds * 1000
                    ),
                },
                correlation_id=trace.run_id,
            )

            async with self._lock:
                self._active_runs.pop(
                    trace.run_id,
                    None,
                )

        return self._build_result(trace)

    @staticmethod
    def _safe_context(
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if context is None:
            return {}

        if not isinstance(context, Mapping):
            raise TypeError(
                "Runtime context must be a mapping"
            )

        return {
            str(key)[:100]: str(value)[:500]
            for key, value in list(context.items())[:30]
}
    async def _execute_step(
        self,
        trace: RuntimeTrace,
        step: RuntimeStep,
        index: int,
        remaining: float,
        stop: asyncio.Event | None,
    ) -> str:
        started = time.monotonic()

        timeout = min(
            remaining,
            self.limits.max_step_seconds,
        )

        if step.timeout_seconds is not None:
            timeout = min(
                timeout,
                step.timeout_seconds,
            )

        trace.tool_calls += 1

        try:
            callback_result = step.callback()

            if inspect.isawaitable(callback_result):
                task = asyncio.ensure_future(
                    callback_result
                )
            else:
                async def resolve_result() -> Any:
                    return await asyncio.to_thread(
                        lambda: callback_result
                    )

                task = asyncio.create_task(
                    resolve_result()
                )

            if stop is None:
                result = await asyncio.wait_for(
                    task,
                    timeout=timeout,
                )
            else:
                stop_task = asyncio.create_task(
                    stop.wait()
                )

                try:
                    done, _ = await asyncio.wait(
                        {task, stop_task},
                        timeout=timeout,
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    if stop_task in done and stop.is_set():
                        task.cancel()
                        await asyncio.gather(
                            task,
                            return_exceptions=True,
                        )
                        return "cancelled"

                    if task not in done:
                        task.cancel()
                        await asyncio.gather(
                            task,
                            return_exceptions=True,
                        )
                        return "timeout"

                    result = await task

                finally:
                    if not stop_task.done():
                        stop_task.cancel()

                    await asyncio.gather(
                        stop_task,
                        return_exceptions=True,
                    )

            output = str(result)

            if len(output) > self.limits.max_output_chars:
                output = (
                    output[:self.limits.max_output_chars]
                    + "...[truncated]"
                )

            elapsed = time.monotonic() - started

            trace.steps.append(
                {
                    "index": index,
                    "name": step.name,
                    "status": "done",
                    "elapsed_ms": int(elapsed * 1000),
                    "result": output,
                }
            )

            await self._publish(
                "runtime.step.completed",
                {
                    "run_id": trace.run_id,
                    "index": index,
                    "name": step.name,
                    "elapsed_ms": int(elapsed * 1000),
                },
                correlation_id=trace.run_id,
            )

            return "completed"

        except asyncio.CancelledError:
            trace.steps.append(
                {
                    "index": index,
                    "name": step.name,
                    "status": "cancelled",
                }
            )
            raise

        except asyncio.TimeoutError:
            trace.steps.append(
                {
                    "index": index,
                    "name": step.name,
                    "status": "timeout",
                    "elapsed_ms": int(
                        (time.monotonic() - started) * 1000
                    ),
                }
            )

            await self._publish(
                "runtime.step.timeout",
                {
                    "run_id": trace.run_id,
                    "index": index,
                    "name": step.name,
                },
                correlation_id=trace.run_id,
            )

            return "timeout"

        except Exception as exc:
            error = (
                f"{type(exc).__name__}: {str(exc)[:300]}"
            )

            trace.error = error

            trace.steps.append(
                {
                    "index": index,
                    "name": step.name,
                    "status": "failed",
                    "error": error,
                    "elapsed_ms": int(
                        (time.monotonic() - started) * 1000
                    ),
                }
            )

            logger.exception(
                "Runtime step failed: %s",
                step.name,
            )

            await self._publish(
                "runtime.step.failed",
                {
                    "run_id": trace.run_id,
                    "index": index,
                    "name": step.name,
                    "error": error,
                },
                correlation_id=trace.run_id,
            )

            return "failed"

    async def _publish(
        self,
        event_name: str,
        payload: Mapping[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> None:
        try:
            event = AgentEvent(
                name=event_name,
                payload=dict(payload),
                correlation_id=correlation_id,
            )

            await self.events.publish(event)

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "Runtime event publishing failed: %s",
                event_name,
            )

    def _build_result(
        self,
        trace: RuntimeTrace,
    ) -> dict[str, Any]:
        return {
            "run_id": trace.run_id,
            "status": trace.status,
            "steps": trace.steps,
            "elapsed_ms": int(
                trace.elapsed_seconds * 1000
            ),
            "tool_calls": trace.tool_calls,
            "error": trace.error,
        }

    async def get_active_runs(
        self,
    ) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {
                    "run_id": trace.run_id,
                    "status": trace.status,
                    "elapsed_ms": int(
                        trace.elapsed_seconds * 1000
                    ),
                    "steps_completed": len(trace.steps),
                    "tool_calls": trace.tool_calls,
                }
                for trace in self._active_runs.values()
            ]

    async def shutdown(self) -> None:
        if self._closed:
            return

        self._closed = True

        await self._publish(
            "runtime.shutdown",
            {
                "active_runs": self.active_runs,
            },
        )

        logger.info(
            "AgentRuntime shutdown requested"
        )

    async def __aenter__(self) -> AgentRuntime:
        if self._closed:
            raise RuntimeClosedError(
                "Runtime is closed"
            )

        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.shutdown()


__all__ = [
    "RuntimeErrorBase",
    "RuntimeBudgetExceeded",
    "RuntimeClosedError",
    "RuntimeStepError",
    "RuntimeLimits",
    "RuntimeTrace",
    "RuntimeStep",
    "AgentRuntime",
          ]
          

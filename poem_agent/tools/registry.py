
from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Mapping

from security.policy_engine import ActionRisk, PolicyEngine


logger = logging.getLogger(__name__)

ToolHandler = Callable[
    [dict[str, Any]],
    Any | Awaitable[Any],
]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler

    risk: ActionRisk = ActionRisk.EXTERNAL

    required: tuple[str, ...] = ()

    max_input_chars: int = 4000
    timeout_seconds: float = 20.0

    version: str = "1"

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    def validate(self) -> None:
        if not isinstance(self.name, str):
            raise TypeError("Tool name must be a string")

        if not re.fullmatch(
            r"[a-z][a-z0-9_]{1,48}",
            self.name,
        ):
            raise ValueError("Invalid tool name")

        if (
            not isinstance(self.description, str)
            or not self.description.strip()
            or len(self.description) > 500
        ):
            raise ValueError("Invalid tool description")

        if not callable(self.handler):
            raise TypeError("Tool handler must be callable")

        if not isinstance(self.risk, ActionRisk):
            raise TypeError("Invalid tool risk level")

        if not 100 <= self.max_input_chars <= 50000:
            raise ValueError("Tool input limit out of range")

        if not 0.1 <= self.timeout_seconds <= 300:
            raise ValueError("Tool timeout out of range")

        if not self.version or len(self.version) > 30:
            raise ValueError("Invalid tool version")

        if len(self.required) > 50:
            raise ValueError("Too many required arguments")

        if any(
            not isinstance(item, str) or not item
            for item in self.required
        ):
            raise ValueError("Invalid required argument")

        if len(set(self.required)) != len(self.required):
            raise ValueError("Duplicate required arguments")

        if not isinstance(self.metadata, Mapping):
            raise TypeError("Tool metadata must be a mapping")


@dataclass(frozen=True, slots=True)
class ToolExecution:
    name: str
    ok: bool
    output: Any
    elapsed_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "output": self.output,
            "elapsed_ms": self.elapsed_ms,
            "error": self.error,
        }


class ToolRegistry:
    """Central registry for trusted executable tools."""

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        *,
        max_tools: int = 200,
        default_timeout: float = 20.0,
    ) -> None:
        self.policy = policy or PolicyEngine()

        self.max_tools = max(
            1,
            min(int(max_tools), 1000),
        )

        self.default_timeout = max(
            0.1,
            min(float(default_timeout), 300.0),
        )

        self._items: dict[str, ToolDefinition] = {}

        self._lock = asyncio.Lock()

        self._closed = False

        self._executions = 0
        self._successes = 0
        self._failures = 0

    @property
    def count(self) -> int:
        return len(self._items)

    @property
    def is_closed(self) -> bool:
        return self._closed

    async def register(
        self,
        definition: ToolDefinition,
    ) -> None:
        if self._closed:
            raise RuntimeError("Tool registry is closed")

        if not isinstance(definition, ToolDefinition):
            raise TypeError(
                "Expected a ToolDefinition instance"
            )

        definition.validate()

        async with self._lock:
            if definition.name in self._items:
                raise ValueError(
                    f"Tool already registered: {definition.name}"
                )

            if len(self._items) >= self.max_tools:
                raise RuntimeError(
                    "Tool registry capacity reached"
                )

            self._items[definition.name] = definition

    async def unregister(
        self,
        name: str,
    ) -> bool:
        async with self._lock:
            return self._items.pop(name, None) is not None

    def get(
        self,
        name: str,
    ) -> ToolDefinition | None:
        return self._items.get(name)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "description": item.description,
                "risk": item.risk.value,
                "required": list(item.required),
                "version": item.version,
            }
            for item in self._items.values()
        ]

    def contains(self, name: str) -> bool:
        return name in self._items

    def is_read_only(self, name: str) -> bool:
        definition = self._items.get(name)

        return bool(
            definition
            and definition.risk == ActionRisk.READ
        )

    def _validate_arguments(
        self,
        definition: ToolDefinition,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise ValueError(
                "Tool arguments must be an object"
            )

        payload = dict(arguments)

        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Tool arguments are not serializable"
            ) from exc

        if len(encoded) > definition.max_input_chars:
            raise ValueError(
                "Tool arguments exceed the input limit"
            )

        missing = [
            key
            for key in definition.required
            if key not in payload
        ]

        if missing:
            raise ValueError(
                "Missing required arguments: "
                + ", ".join(missing)
            )

        return payload
          def _is_authorized(
        self,
        definition: ToolDefinition,
        approved: bool,
    ) -> tuple[bool, str]:
        if definition.risk == ActionRisk.READ:
            return True, "Read-only action"

        if (
            definition.risk == ActionRisk.INTERNAL_WRITE
            and self.policy.allow_internal_writes
        ):
            return True, "Internal write permitted"

        if approved:
            return True, "Owner approval provided"

        return False, "Owner approval required"

    async def _invoke_handler(
        self,
        definition: ToolDefinition,
        arguments: dict[str, Any],
    ) -> Any:
        handler = definition.handler

        if inspect.iscoroutinefunction(handler):
            return await asyncio.wait_for(
                handler(arguments),
                timeout=definition.timeout_seconds,
            )

        result = await asyncio.wait_for(
            asyncio.to_thread(handler, arguments),
            timeout=definition.timeout_seconds,
        )

        if inspect.isawaitable(result):
            return await asyncio.wait_for(
                result,
                timeout=definition.timeout_seconds,
            )

        return result

    async def execute(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        approved: bool = False,
    ) -> ToolExecution:
        started = time.monotonic()

        if self._closed:
            return ToolExecution(
                name=name,
                ok=False,
                output=None,
                elapsed_ms=0,
                error="Tool registry is closed",
            )

        definition = self._items.get(name)

        if definition is None:
            self._failures += 1
            return ToolExecution(
                name=name,
                ok=False,
                output=None,
                elapsed_ms=0,
                error=f"Unknown tool: {name}",
            )

        try:
            payload = self._validate_arguments(
                definition,
                arguments or {},
            )

            authorized, reason = self._is_authorized(
                definition,
                approved,
            )

            if not authorized:
                raise PermissionError(reason)

            timeout = min(
                definition.timeout_seconds,
                self.default_timeout,
            )

            execution_definition = definition

            if timeout != definition.timeout_seconds:
                execution_definition = ToolDefinition(
                    name=definition.name,
                    description=definition.description,
                    handler=definition.handler,
                    risk=definition.risk,
                    required=definition.required,
                    max_input_chars=definition.max_input_chars,
                    timeout_seconds=timeout,
                    version=definition.version,
                    metadata=definition.metadata,
                )

            output = await self._invoke_handler(
                execution_definition,
                payload,
            )

            elapsed_ms = int(
                (time.monotonic() - started) * 1000
            )

            self._executions += 1
            self._successes += 1

            return ToolExecution(
                name=name,
                ok=True,
                output=output,
                elapsed_ms=elapsed_ms,
            )

        except asyncio.CancelledError:
            raise

        except asyncio.TimeoutError:
            elapsed_ms = int(
                (time.monotonic() - started) * 1000
            )

            self._executions += 1
            self._failures += 1

            return ToolExecution(
                name=name,
                ok=False,
                output=None,
                elapsed_ms=elapsed_ms,
                error="Tool execution timed out",
            )

        except PermissionError as exc:
            elapsed_ms = int(
                (time.monotonic() - started) * 1000
            )

            self._executions += 1
            self._failures += 1

            return ToolExecution(
                name=name,
                ok=False,
                output=None,
                elapsed_ms=elapsed_ms,
                error=str(exc),
            )

        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            elapsed_ms = int(
                (time.monotonic() - started) * 1000
            )

            self._executions += 1
            self._failures += 1

            return ToolExecution(
                name=name,
                ok=False,
                output=None,
                elapsed_ms=elapsed_ms,
                error=f"Invalid tool input: {exc}",
            )

        except Exception as exc:
            elapsed_ms = int(
                (time.monotonic() - started) * 1000
            )

            self._executions += 1
            self._failures += 1

            logger.exception(
                "Tool execution failed: %s",
                name,
            )

            return ToolExecution(
                name=name,
                ok=False,
                output=None,
                elapsed_ms=elapsed_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

    def metrics(self) -> dict[str, Any]:
        success_rate = (
            self._successes / self._executions
            if self._executions
            else 0.0
        )

        return {
            "registered_tools": len(self._items),
            "executions": self._executions,
            "successes": self._successes,
            "failures": self._failures,
            "success_rate": round(success_rate, 4),
            "closed": self._closed,
            "max_tools": self.max_tools,
        }

    async def close(self) -> None:
        if self._closed:
            return

        async with self._lock:
            self._closed = True

    async def __aenter__(self) -> "ToolRegistry":
        if self._closed:
            raise RuntimeError(
                "Cannot enter a closed tool registry"
            )

        return self

    async def __aexit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> None:
        await self.close()


__all__ = [
    "ToolDefinition",
    "ToolExecution",
    "ToolRegistry",
    "ToolHandler",
]

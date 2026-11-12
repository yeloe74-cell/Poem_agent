"""Typed safe tool registry; arbitrary code execution is not supported."""
from dataclasses import dataclass
from typing import Callable, Any


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Callable[..., Any]
    owner_only: bool = True
    approval_action: str | None = None


class ToolManager:
    def __init__(self, permissions):
        self.permissions = permissions
        self.tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        if not tool.name or tool.name in self.tools:
            raise ValueError("tool name must be unique and non-empty")
        self.tools[tool.name] = tool

    async def execute(self, name, actor_id, arguments, approved=False):
        tool = self.tools.get(name)
        if not tool:
            raise KeyError(name)
        if tool.owner_only or tool.approval_action:
            self.permissions.authorize(actor_id, tool.approval_action or "tool", approved=approved)
        result = tool.handler(**arguments)
        if hasattr(result, "__await__"):
            result = await result
        return result

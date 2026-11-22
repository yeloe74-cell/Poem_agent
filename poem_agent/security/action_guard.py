
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Risk(str, Enum):
    READ = "read"
    WRITE = "write"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    requires_approval: bool
    reason: str


class ActionGuard:
    """Controls whether registered agent tools may perform actions."""

    DEFAULT_RISK = {
        "calculate": Risk.READ,
        "list_tasks": Risk.READ,
        "recall": Risk.READ,
        "search_knowledge": Risk.READ,
        "create_plan": Risk.READ,
        "workflow_status": Risk.READ,
        "project_status": Risk.READ,
        "ingest_knowledge": Risk.WRITE,
        "create_workflow": Risk.WRITE,
        "request_workflow_execution": Risk.WRITE,
        "create_task": Risk.WRITE,
        "update_task": Risk.WRITE,
        "remember": Risk.WRITE,
        "publish": Risk.EXTERNAL,
        "publish_post": Risk.EXTERNAL,
        "send_message": Risk.EXTERNAL,
        "remove_source": Risk.DESTRUCTIVE,
        "delete_data": Risk.DESTRUCTIVE,
        "change_credentials": Risk.DESTRUCTIVE,
    }

    def __init__(
        self,
        allowed_tools: Iterable[str] = (),
        *,
        auto_allow_read: bool = True,
        auto_allow_internal_write: bool = True,
    ) -> None:
        self.allowed_tools = frozenset(
            name.strip()
            for name in allowed_tools
            if isinstance(name, str) and name.strip()
        )

        self.auto_allow_read = bool(auto_allow_read)
        self.auto_allow_internal_write = bool(
            auto_allow_internal_write
        )

    def assess(
        self,
        tool_name: str,
        *,
        owner_confirmed: bool = False,
        explicitly_allowed: bool = False,
    ) -> Decision:
        if (
            not isinstance(tool_name, str)
            or not tool_name.strip()
        ):
            return Decision(
                False,
                False,
                "invalid tool name",
            )

        tool_name = tool_name.strip()

        if tool_name not in self.allowed_tools:
            return Decision(
                False,
                False,
                "tool is not in the trusted allow-list",
            )

        risk = self.DEFAULT_RISK.get(
            tool_name,
            Risk.EXTERNAL,
        )

        if risk == Risk.READ:
            if self.auto_allow_read:
                return Decision(
                    True,
                    False,
                    "read-only action is allowed",
                )

            return Decision(
                False,
                True,
                "read action requires approval",
            )

        if risk == Risk.WRITE:
            if self.auto_allow_internal_write:
                return Decision(
                    True,
                    False,
                    "internal reversible action is allowed",
                )

            if owner_confirmed and explicitly_allowed:
                return Decision(
                    True,
                    False,
                    "internal write explicitly approved",
                )

            return Decision(
                False,
                True,
                "internal write requires owner approval",
            )

        if not owner_confirmed:
            return Decision(
                False,
                True,
                "owner confirmation is required",
            )

        if not explicitly_allowed:
            return Decision(
                False,
                True,
                "explicit permission is required",
            )

        return Decision(
            True,
            False,
            "action is permitted",
        )

    def require(
        self,
        tool_name: str,
        *,
        owner_confirmed: bool = False,
        explicitly_allowed: bool = False,
    ) -> None:
        decision = self.assess(
            tool_name,
            owner_confirmed=owner_confirmed,
            explicitly_allowed=explicitly_allowed,
        )

        if not decision.allowed:
            raise PermissionError(decision.reason)

    def describe(self) -> dict[str, str]:
        return {
            name: self.DEFAULT_RISK.get(
                name,
                Risk.EXTERNAL,
            ).value
            for name in sorted(self.allowed_tools)
        }


__all__ = [
    "Risk",
    "Decision",
    "ActionGuard",
      ]
      

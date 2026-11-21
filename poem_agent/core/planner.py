
from __future__ import annotations

import json
import re
import uuid

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from core.errors import AIError


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    title: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    requires_approval: bool = False


@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    goal: str
    steps: tuple[PlanStep, ...]
    created_at: str
    status: str = "proposed"

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [asdict(step) for step in self.steps],
            "created_at": self.created_at,
            "status": self.status,
        }


class PlanValidationError(ValueError):
    pass


class Planner:
    SYSTEM = """Create a practical and minimal execution plan.

Return only a valid JSON object:
{
  "goal": "string",
  "steps": [
    {
      "title": "string",
      "tool": "registered_tool_name",
      "arguments": {},
      "depends_on": [],
      "requires_approval": false
    }
  ]
}

Rules:
- Use only the supplied tool names.
- Never invent tools.
- Do not generate shell commands or arbitrary code.
- Do not request credentials or private keys.
- Prefer read-only operations before changes.
- Mark external, destructive, or irreversible actions
  as requiring owner approval.
- Dependencies must reference earlier step IDs.
- Keep the plan minimal and practical.
- A plan is a proposal and must never execute itself.
"""

    MAX_GOAL_LENGTH = 1800
    MAX_TITLE_LENGTH = 180
    MAX_ARGUMENT_LENGTH = 2000
    MAX_CONTEXT_LENGTH = 12000

    FORBIDDEN_ARGUMENTS = re.compile(
        r"(?i)(api[_ -]?key|password|secret|private[_ -]?key|"
        r"seed phrase|otp|access[_ -]?token|refresh[_ -]?token)"
    )

    def __init__(
        self,
        brain: Any,
        allowed_tools: Iterable[str],
        *,
        max_steps: int = 12,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")

        self.brain = brain
        self.allowed_tools = frozenset(
            str(tool).strip()
            for tool in allowed_tools
            if str(tool).strip()
        )
        self.max_steps = min(int(max_steps), 20)

    async def create(
        self,
        goal: str,
        context: Mapping[str, Any] | None = None,
    ) -> ExecutionPlan:
        if not isinstance(goal, str):
            raise PlanValidationError("goal must be a string")

        goal = goal.strip()

        if not goal or len(goal) > self.MAX_GOAL_LENGTH:
            raise PlanValidationError(
                "goal must contain 1-1800 characters"
            )

        if not getattr(self.brain, "available", False):
            raise AIError("AI provider is not available")

        if context is not None and not isinstance(context, Mapping):
            raise PlanValidationError("context must be a mapping")

        prompt = {
            "goal": goal,
            "context": dict(context or {}),
            "allowed_tools": sorted(self.allowed_tools),
            "limits": {
                "max_steps": self.max_steps,
                "no_auto_execution": True,
            },
        }

        try:
            user_message = json.dumps(
                prompt,
                ensure_ascii=False,
                default=str,
            )
        except (TypeError, ValueError) as exc:
            raise PlanValidationError(
                "context cannot be serialized"
            ) from exc

        if len(user_message) > self.MAX_CONTEXT_LENGTH:
            raise PlanValidationError("planning context is too large")

        raw, _model = await self.brain.complete(
            "conversation",
            self.SYSTEM,
            user_message,
            max_tokens=1100,
            temperature=0.1,
        )

        payload = self._decode(raw)
        return self.validate(payload)

    @staticmethod
    def _decode(raw: str) -> dict[str, Any]:
        if not isinstance(raw, str):
            raise PlanValidationError(
                "AI response must be a string"
            )

        text = raw.strip()

        if text.startswith("```"):
            text = re.sub(
                r"\A```(?:json)?\s*",
                "",
                text,
                flags=re.IGNORECASE,
            )
            text = re.sub(r"\s*```\Z", "", text)

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")

            if start < 0 or end <= start:
                raise PlanValidationError(
                    "AI did not return a JSON object"
                )

            try:
                payload = json.loads(text[start:end + 1])
            except json.JSONDecodeError as exc:
                raise PlanValidationError(
                    "AI returned invalid JSON"
                ) from exc

        if not isinstance(payload, dict):
            raise PlanValidationError(
                "plan must be a JSON object"
            )

        return payload

    def validate(
        self,
        payload: Mapping[str, Any],
    ) -> ExecutionPlan:
        if not isinstance(payload, Mapping):
            raise PlanValidationError(
                "plan payload must be a mapping"
            )

        goal = payload.get("goal")
        raw_steps = payload.get("steps")

        if (
            not isinstance(goal, str)
            or not goal.strip()
            or len(goal) > self.MAX_GOAL_LENGTH
        ):
            raise PlanValidationError(
                "plan goal is missing or invalid"
            )

        if (
            not isinstance(raw_steps, list)
            or not 1 <= len(raw_steps) <= self.max_steps
        ):
            raise PlanValidationError(
                f"plan must contain 1-{self.max_steps} steps"
            )

        steps: list[PlanStep] = []
        known_steps: set[str] = set()

        for index, raw in enumerate(raw_steps, start=1):
            if not isinstance(raw, dict):
                raise PlanValidationError(
                    f"step {index} must be an object"
                )

            title = raw.get("title")
            tool = raw.get("tool")
            arguments = raw.get("arguments", {})
            dependencies = raw.get("depends_on", [])
            approval = raw.get("requires_approval", False)

            if (
                not isinstance(title, str)
                or not title.strip()
                or len(title) > self.MAX_TITLE_LENGTH
            ):
                raise PlanValidationError(
                    f"step {index} has an invalid title"
                )

            if not isinstance(tool, str) or tool not in self.allowed_tools:
                raise PlanValidationError(
                    f"step {index} uses an unavailable tool"
                )

            if not isinstance(arguments, dict):
                raise PlanValidationError(
                    f"step {index} arguments must be an object"
                )

            try:
                serialized_arguments = json.dumps(
                    arguments,
                    ensure_ascii=False,
                    default=str,
                )
            except (TypeError, ValueError) as exc:
                raise PlanValidationError(
                    f"step {index} arguments cannot be serialized"
                ) from exc

            if len(serialized_arguments) > self.MAX_ARGUMENT_LENGTH:
                raise PlanValidationError(
                    f"step {index} arguments are too large"
                )

            if (
                not isinstance(dependencies, list)
                or len(dependencies) > self.max_steps
            ):
                raise PlanValidationError(
                    f"step {index} dependencies are invalid"
                )

            if any(
                not isinstance(dependency, str)
                for dependency in dependencies
            ):
                raise PlanValidationError(
                    f"step {index} dependency IDs must be strings"
                )

            if type(approval) is not bool:
                raise PlanValidationError(
                    f"step {index} approval flag must be boolean"
                )

            step_id = f"s{index}"

            step = PlanStep(
                step_id=step_id,
                title=title.strip(),
                tool=tool,
                arguments=dict(arguments),
                depends_on=tuple(dependencies),
                requires_approval=approval,
            )

            steps.append(step)
            known_steps.add(step_id)

        self._validate_dependencies(steps, known_steps)
        self._validate_sensitive_arguments(steps)

        return ExecutionPlan(
            plan_id=uuid.uuid4().hex[:16],
            goal=goal.strip(),
            steps=tuple(steps),
            created_at=datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        )

    @staticmethod
    def _validate_dependencies(
        steps: list[PlanStep],
        known_steps: set[str],
    ) -> None:
        for step in steps:
            if len(set(step.depends_on)) != len(step.depends_on):
                raise PlanValidationError(
                    f"step {step.step_id} repeats a dependency"
                )

            for dependency in step.depends_on:
                if dependency not in known_steps:
                    raise PlanValidationError(
                        f"step {step.step_id} has an unknown dependency"
                    )

                if dependency == step.step_id:
                    raise PlanValidationError(
                        f"step {step.step_id} cannot depend on itself"
                    )

                if int(dependency[1:]) >= int(step.step_id[1:]):
                    raise PlanValidationError(
                        "dependencies must reference earlier steps"
                    )

    def _validate_sensitive_arguments(
        self,
        steps: list[PlanStep],
    ) -> None:
        for step in steps:
            serialized = json.dumps(
                step.arguments,
                ensure_ascii=False,
                default=str,
            )

            if self.FORBIDDEN_ARGUMENTS.search(serialized):
                raise PlanValidationError(
                    "plan arguments must not contain credentials"
                )

    @staticmethod
    def render(plan: ExecutionPlan) -> str:
        lines = [
            f"အစီအစဉ်: {plan.goal}",
            f"Plan ID: {plan.plan_id}",
        ]

        for step in plan.steps:
            details = [f"{step.step_id}. {step.title} [{step.tool}]"]

            if step.depends_on:
                details.append(
                    f"Depends on {', '.join(step.depends_on)}"
                )

            if step.requires_approval:
                details.append("Owner approval လိုမယ်")

            lines.append(" · ".join(details))

        lines.append(
            "ဒီအစီအစဉ်ဟာ အဆိုပြုချက်သာဖြစ်ပြီး "
            "အလိုအလျောက် မလုပ်ဆောင်ပါဘူး။"
        )

        return "\n".join(lines)
      

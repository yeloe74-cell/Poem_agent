
"""Evaluate agent outcomes and create safe reflection records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class Evaluation:
    status: str
    score: float
    reasons: tuple[str, ...]
    retryable: bool

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": self.score,
            "reasons": list(self.reasons),
            "retryable": self.retryable,
        }


class OutcomeEvaluator:
    """Evaluate execution evidence without trusting assistant claims."""

    SUCCESS_STATES = frozenset({
        "done",
        "completed",
        "published",
        "ok",
        "success",
        "verified",
    })

    FAILURE_STATES = frozenset({
        "failed",
        "error",
        "rejected",
        "cancelled",
        "canceled",
        "timeout",
    })

    RETRYABLE_STATES = frozenset({
        "failed",
        "error",
        "timeout",
    })

    MAX_REASON_LENGTH = 500
    MAX_EXPECTED_FIELDS = 40
    MAX_EVIDENCE_FIELDS = 30
    MAX_KEY_LENGTH = 100
    MAX_VALUE_LENGTH = 500

    SECRET_PATTERN = re.compile(
        r"(?i)\b(api[_ -]?key|access[_ -]?token|"
        r"refresh[_ -]?token|password|secret|"
        r"private[_ -]?key|authorization)\b"
        r"(\s*[:=]\s*|\s+)([^\s,;]+)"
    )

    SECRET_KEYS = frozenset({
        "api_key",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "private_key",
        "authorization",
        "otp",
        "seed_phrase",
    })

    def evaluate(
        self,
        *,
        expected: Sequence[str],
        observed: Mapping[str, Any],
        error: str | None = None,
    ) -> Evaluation:
        """Compare expected evidence with the actual execution result."""

        if not isinstance(observed, Mapping):
            return Evaluation(
                status="needs_review",
                score=0.0,
                reasons=("Execution evidence is invalid",),
                retryable=False,
            )

        if error:
            return Evaluation(
                status="failed",
                score=0.0,
                reasons=(self._safe_text(error),),
                retryable=True,
            )

        state = str(observed.get("status", "unknown")).strip().lower()

        if state in self.FAILURE_STATES:
            return Evaluation(
                status="failed",
                score=0.0,
                reasons=(f"Execution status: {state}",),
                retryable=state in self.RETRYABLE_STATES,
            )

        fields = list(expected)[: self.MAX_EXPECTED_FIELDS]
        missing = [
            key
            for key in fields
            if key not in observed
            or observed[key] is None
            or observed[key] == ""
        ]

        reasons: list[str] = []

        if missing:
            names = ", ".join(
                self._safe_text(str(key))[: self.MAX_KEY_LENGTH]
                for key in missing[:10]
            )
            reasons.append(f"Missing evidence: {names}")

        confirmed = state in self.SUCCESS_STATES

        if not confirmed:
            reasons.append("Completion status is not confirmed")

        score = 1.0
        score -= min(len(missing) * 0.2, 0.8)

        if not confirmed:
            score -= 0.3

        score = round(max(0.0, min(score, 1.0)), 3)

        verified = confirmed and not missing

        if verified:
            reasons.append("All required evidence is present")

        return Evaluation(
            status="verified" if verified else "needs_review",
            score=score,
            reasons=tuple(reasons),
            retryable=False,
        )

    @classmethod
    def reflection_payload(
        cls,
        goal: str,
        evaluation: Evaluation,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create a bounded, sanitized record for reflection storage."""

        safe_evidence: dict[str, str] = {}

        for key, value in list(evidence.items())[: cls.MAX_EVIDENCE_FIELDS]:
            safe_key = str(key)[: cls.MAX_KEY_LENGTH]

            if safe_key.lower() in cls.SECRET_KEYS:
                safe_evidence[safe_key] = "[REDACTED]"
                continue

            safe_evidence[safe_key] = cls._safe_text(
                cls._stringify(value)
            )[: cls.MAX_VALUE_LENGTH]

        return {
            "goal": cls._safe_text(str(goal))[:1000],
            "status": evaluation.status,
            "score": evaluation.score,
            "retryable": evaluation.retryable,
            "reasons": [
                cls._safe_text(reason)[: cls.MAX_REASON_LENGTH]
                for reason in evaluation.reasons[:10]
            ],
            "evidence": safe_evidence,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _stringify(value: Any) -> str:
        if isinstance(value, (dict, list, tuple, set)):
            return str(value)

        return str(value)

    @classmethod
    def _safe_text(cls, value: str) -> str:
        """Remove common credential patterns before storing text."""

        return cls.SECRET_PATTERN.sub(
            lambda match: f"{match.group(1)}=[REDACTED]",
            str(value),
      )
      

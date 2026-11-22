from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Iterable


class ActionRisk(str, Enum):
    READ = "read"
    INTERNAL_WRITE = "internal_write"
    EXTERNAL = "external"
    DESTRUCTIVE = "destructive"
    CREDENTIAL = "credential"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    approval_required: bool
    reason: str


class ApprovalVault:
    """Stores short-lived, scoped, single-use approval tokens."""

    def __init__(
        self,
        *,
        ttl_seconds: int = 180,
        max_tokens: int = 10000,
    ) -> None:
        self.ttl = max(15, min(int(ttl_seconds), 900))
        self.max_tokens = max(100, min(int(max_tokens), 100000))
        self._tokens: dict[str, tuple[str, float]] = {}
        self._lock = RLock()

    def issue(self, action: str, subject: str) -> str:
        if not isinstance(action, str) or not action.strip():
            raise ValueError("Action must be a non-empty string")

        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Subject must be a non-empty string")

        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        scope = f"{action}:{subject}"
        expires = time.monotonic() + self.ttl

        with self._lock:
            self._purge_locked()

            if len(self._tokens) >= self.max_tokens:
                oldest = min(
                    self._tokens,
                    key=lambda key: self._tokens[key][1],
                )
                self._tokens.pop(oldest, None)

            self._tokens[digest] = (scope, expires)

        return token

    def consume(
        self,
        token: str,
        action: str,
        subject: str,
    ) -> bool:
        if (
            not isinstance(token, str)
            or not token
            or len(token) > 200
        ):
            return False

        digest = hashlib.sha256(token.encode()).hexdigest()
        expected_scope = f"{action}:{subject}"

        with self._lock:
            record = self._tokens.pop(digest, None)

            if record is None:
                return False

            scope, expires = record

            if time.monotonic() > expires:
                return False

            return hmac.compare_digest(
                scope,
                expected_scope,
            )

    def revoke(self, token: str) -> bool:
        if not isinstance(token, str) or not token:
            return False

        digest = hashlib.sha256(token.encode()).hexdigest()

        with self._lock:
            return self._tokens.pop(digest, None) is not None

    def revoke_all(self) -> int:
        with self._lock:
            count = len(self._tokens)
            self._tokens.clear()
            return count

    def _purge_locked(self) -> None:
        now = time.monotonic()

        self._tokens = {
            key: value
            for key, value in self._tokens.items()
            if value[1] > now
        }

    def purge(self) -> int:
        with self._lock:
            before = len(self._tokens)
            self._purge_locked()
            return before - len(self._tokens)

    @property
    def count(self) -> int:
        with self._lock:
            self._purge_locked()
            return len(self._tokens)


class PolicyEngine:
    """Default-deny policy for registered actions and risky capabilities."""

    DEFAULT = {
        "read": ActionRisk.READ,
        "search": ActionRisk.READ,
        "calculate": ActionRisk.READ,
        "create_plan": ActionRisk.READ,
        "create_task": ActionRisk.INTERNAL_WRITE,
        "update_task": ActionRisk.INTERNAL_WRITE,
        "remember": ActionRisk.INTERNAL_WRITE,
        "publish": ActionRisk.EXTERNAL,
        "publish_post": ActionRisk.EXTERNAL,
        "send_message": ActionRisk.EXTERNAL,
        "delete": ActionRisk.DESTRUCTIVE,
        "delete_data": ActionRisk.DESTRUCTIVE,
        "remove_source": ActionRisk.DESTRUCTIVE,
        "change_credentials": ActionRisk.CREDENTIAL,
    }

    def __init__(
        self,
        allowed: Iterable[str] = (),
        *,
        allow_internal_writes: bool = True,
    ) -> None:
        self.allowed = frozenset(
            str(item).strip()
            for item in allowed
            if str(item).strip()
        )
        self.allow_internal_writes = bool(
            allow_internal_writes
        )

    def assess(
        self,
        action: str,
        *,
        approval_token: str | None = None,
        subject: str = "default",
        vault: ApprovalVault | None = None,
    ) -> PolicyDecision:
        if not isinstance(action, str) or not action.strip():
            return PolicyDecision(
                False,
                False,
                "invalid action name",
            )

        action = action.strip()

        if action not in self.allowed:
            return PolicyDecision(
                False,
                False,
                "action is not allow-listed",
            )

        risk = self.DEFAULT.get(
            action,
            ActionRisk.EXTERNAL,
        )

        if risk == ActionRisk.READ:
            return PolicyDecision(
                True,
                False,
                "read-only action allowed",
            )

        if (
            risk == ActionRisk.INTERNAL_WRITE
            and self.allow_internal_writes
        ):
            return PolicyDecision(
                True,
                False,
                "reversible internal action allowed",
            )

        if (
            approval_token
            and vault
            and vault.consume(
                approval_token,
                action,
                subject,
            )
        ):
            return PolicyDecision(
                True,
                False,
                "scoped owner approval accepted",
            )

        return PolicyDecision(
            False,
            True,
            f"{risk.value} action requires explicit owner approval",
        )

    def require(
        self,
        action: str,
        *,
        approval_token: str | None = None,
        subject: str = "default",
        vault: ApprovalVault | None = None,
    ) -> None:
        decision = self.assess(
            action,
            approval_token=approval_token,
            subject=subject,
            vault=vault,
        )

        if not decision.allowed:
            raise PermissionError(decision.reason)

    def describe(self) -> dict[str, str]:
        return {
            name: self.DEFAULT.get(
                name,
                ActionRisk.EXTERNAL,
            ).value
            for name in sorted(self.allowed)
        }


__all__ = [
    "ActionRisk",
    "PolicyDecision",
    "ApprovalVault",
    "PolicyEngine",
              ]


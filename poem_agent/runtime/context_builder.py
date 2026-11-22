from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_SECRET = re.compile(
    r"(?i)\b(?:api[_ -]?key|password|passwd|secret|"
    r"private[_ -]?key|seed phrase|otp|access[_ -]?token)"
    r"\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


@dataclass(frozen=True, slots=True)
class ContextSection:
    name: str
    content: str
    priority: int = 50
    max_chars: int = 2000

    def validate(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Context section name is required")

        if not isinstance(self.content, str):
            raise TypeError("Context content must be a string")

        if not isinstance(self.priority, int):
            raise TypeError("Context priority must be an integer")

        if not isinstance(self.max_chars, int):
            raise TypeError("max_chars must be an integer")

        if self.max_chars < 0:
            raise ValueError("max_chars cannot be negative")


class ContextBuilder:
    """Builds bounded, sanitized context for agent reasoning."""

    def __init__(
        self,
        *,
        total_chars: int = 9000,
        max_sections: int = 12,
    ) -> None:
        self.total_chars = max(
            500,
            min(int(total_chars), 50000),
        )

        self.max_sections = max(
            1,
            min(int(max_sections), 40),
        )

    @staticmethod
    def sanitize(value: Any, limit: int) -> str:
        if limit <= 0:
            return ""

        text = str(value or "")
        text = text.replace("\x00", " ")
        text = text.strip()
        text = _SECRET.sub("[REDACTED]", text)

        return text[:limit]

    def build(
        self,
        sections: Iterable[ContextSection],
    ) -> dict[str, Any]:
        normalized: list[ContextSection] = []

        for section in sections:
            if not isinstance(section, ContextSection):
                raise TypeError(
                    "All sections must be ContextSection instances"
                )

            section.validate()
            normalized.append(section)

        normalized.sort(
            key=lambda item: (
                item.priority,
                item.name.lower(),
            )
        )

        normalized = normalized[:self.max_sections]

        remaining = self.total_chars
        result: list[dict[str, str]] = []
        was_truncated = False

        for section in normalized:
            if remaining <= 0:
                was_truncated = True
                break

            budget = min(
                section.max_chars,
                remaining,
            )

            content = self.sanitize(
                section.content,
                budget,
            )

            if not content:
                continue

            if len(content) < len(section.content.strip()):
                was_truncated = True

            result.append({
                "name": section.name.strip()[:80],
                "content": content,
            })

            remaining -= len(content)

        if len(normalized) < len(list(sections)) if isinstance(sections, list) else False:
            was_truncated = True

        return {
            "sections": result,
            "characters": self.total_chars - remaining,
            "truncated": was_truncated,
        }

    def from_mapping(
        self,
        values: Mapping[str, Any],
        *,
        priority: int = 50,
    ) -> dict[str, Any]:
        sections = []

        for key, value in values.items():
            if value is None or value == "" or value == [] or value == {}:
                continue

            sections.append(
                ContextSection(
                    name=str(key),
                    content=str(value),
                    priority=priority,
                    max_chars=1800,
                )
            )

        return self.build(sections)


__all__ = [
    "ContextSection",
    "ContextBuilder",
      ]


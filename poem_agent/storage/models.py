"""Poem channel domain models and task states."""
from dataclasses import dataclass
from enum import StrEnum


class TaskState(StrEnum):
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Poem:
    id: str
    text: str
    language: str
    author: str | None = None
    source: str | None = None
    emotion: str | None = None


@dataclass(frozen=True)
class Draft:
    id: str
    poem_id: str
    channel_id: str
    text: str
    state: str
    approved_by: int | None = None
    scheduled_at: str | None = None

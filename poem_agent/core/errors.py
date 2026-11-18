
"""Project-wide exception types."""
from __future__ import annotations


class PoemAgentError(Exception):
    """Base class for all Poem Agent errors."""


class ConfigError(PoemAgentError):
    """Missing or invalid configuration."""


class HTTPError(PoemAgentError):
    """HTTP failure. status == 0 means a network-level failure."""

    def __init__(self, status: int, message: str = "") -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


class AIError(PoemAgentError):
    """AI provider failure or unusable AI output."""


class SourceUnavailable(PoemAgentError):
    """A source channel could not be read."""


class PublishError(PoemAgentError):
    """Publishing to the target channel failed."""


class ApprovalRequired(PoemAgentError):
    """An action needs owner approval that has not been given."""


class NotAuthorized(PoemAgentError):
    """The sender is not the configured owner."""
  

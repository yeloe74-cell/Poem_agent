"""Validated environment-backed configuration; no credentials are stored in memory."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    owner_id: int
    database_path: str
    telegram_token: str
    model_provider: str
    model_name: str
    openai_api_key: str
    anthropic_api_key: str
    google_api_key: str
    unsplash_access_key: str
    approval_required: bool

    @classmethod
    def load(cls) -> "Settings":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        try:
            owner_id = int(os.getenv("OWNER_TELEGRAM_ID", "0"))
        except ValueError as exc:
            raise ValueError("OWNER_TELEGRAM_ID must be an integer") from exc
        if owner_id < 0:
            raise ValueError("OWNER_TELEGRAM_ID cannot be negative")
        database_path = os.getenv("DATABASE_PATH", "poem_agent.db").strip()
        if not database_path:
            raise ValueError("DATABASE_PATH cannot be empty")
        return cls(owner_id, str(Path(database_path)), os.getenv("TELEGRAM_BOT_TOKEN", ""),
                   os.getenv("MODEL_PROVIDER", ""), os.getenv("MODEL_NAME", ""),
                   os.getenv("OPENAI_API_KEY", ""), os.getenv("ANTHROPIC_API_KEY", ""),
                   os.getenv("GOOGLE_API_KEY", ""), os.getenv("UNSPLASH_ACCESS_KEY", ""),
                   os.getenv("APPROVAL_REQUIRED", "true").casefold() != "false")

    def provider_key(self, provider: str) -> str:
        return {"openai": self.openai_api_key, "anthropic": self.anthropic_api_key,
                "google": self.google_api_key}.get(provider.casefold(), "")

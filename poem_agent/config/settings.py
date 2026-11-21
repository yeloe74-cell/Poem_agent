
"""Configuration: everything comes from environment variables / a .env file.

No secret is ever written in source code. Use `Settings.from_env()`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from config.constants import DEFAULT_WEEKLY_PLAN, GENERIC_HASHTAGS
from core.errors import ConfigError

AI_TASKS = ("poetry_analysis", "classification", "semantic", "planning", "conversation", "image_query")
PROVIDERS = ("anthropic", "openai", "gemini")

DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "anthropic": {"heavy": "claude-sonnet-5-5", "light": "claude-haiku-5-5"},
    "openai": {"heavy": "gpt-4o", "light": "gpt-4o-mini"},
    "gemini": {"heavy": "gemini-1.5-pro", "light": "gemini-1.5-flash"},
}
LIGHT_TASKS = {"classification", "semantic", "image_query"}

DEFAULT_LICENSE_ALLOW = ("cc0", "public domain", "pd", "cc by", "cc-by", "cc by-sa", "pexels license", "unsplash license")
DEFAULT_LICENSE_BLOCK = ("nc", "nd", "all rights reserved", "fair use")


def load_dotenv(path: Path) -> dict[str, str]:
    """Minimal .env parser (KEY=VALUE, '#' comments, optional quotes)."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key.strip()] = val
    return values


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    normalized = value.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"expected a boolean value, got {value!r}")


def _int(value: str | None, default: int, name: str) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {value!r}") from exc


def _float(value: str | None, default: float, name: str) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value.strip())
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {value!r}") from exc


def _bounded_int(value: str | None, default: int, name: str, minimum: int, maximum: int) -> int:
    result = _int(value, default, name)
    if not minimum <= result <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return result


def _bounded_float(value: str | None, default: float, name: str, minimum: float, maximum: float) -> float:
    result = _float(value, default, name)
    if not minimum <= result <= maximum:
        raise ConfigError(f"{name} must be between {minimum} and {maximum}")
    return result


def _csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None or value.strip() == "":
        return default
    return tuple(p.strip() for p in value.split(",") if p.strip())


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    # Telegram
    api_id: int = 0
    api_hash: str = ""
    bot_token: str = ""
    owner_id: int = 0
    target_channel: str = ""
    # Storage
    db_path: Path = Path("data/poem_agent.db")
    backup_dir: Path = Path("data/backups")
    image_dir: Path = Path("data/images")
    session_dir: Path = Path("data/sessions")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"
    user_agent: str = "PoemAgent/1.0 (poetry channel assistant; set HTTP_USER_AGENT with your contact)"
    # AI
    ai_default_provider: str = "anthropic"
    ai_keys: Mapping[str, str] = field(default_factory=dict)
    ai_base_urls: Mapping[str, str] = field(default_factory=dict)
    task_routes: Mapping[str, tuple[tuple[str, str], ...]] = field(default_factory=dict)
    # Images
    pexels_key: str = ""
    unsplash_key: str = ""
    image_daily_limit: int = 10
    min_image_width: int = 800
    min_image_height: int = 500
    license_allow: tuple[str, ...] = DEFAULT_LICENSE_ALLOW
    license_block: tuple[str, ...] = DEFAULT_LICENSE_BLOCK
    image_ai_judge: bool = True
    # Collection
    scan_interval_minutes: int = 60
    scan_batch_limit: int = 30
    scan_delay_min: float = 5.0
    scan_delay_max: float = 15.0
    min_poem_chars: int = 20
    max_poem_chars: int = 1500
    allow_zawgyi: bool = False
    generic_hashtags: frozenset[str] = GENERIC_HASHTAGS
    dup_similar: float = 0.90
    dup_borderline: float = 0.80
    # Scheduling
    timezone_offset_minutes: int = 390
    post_times: str = "09:00,19:00"
    queue_target: int = 3
    max_batch: int = 10
    stats_interval_hours: int = 6
    show_source_link: bool = False
    weekly_plan: Mapping[int, str] = field(default_factory=lambda: dict(DEFAULT_WEEKLY_PLAN))
    # General Agent runtime
    general_agent_enabled: bool = True
    general_agent_max_calls: int = 3
    general_agent_timeout_seconds: float = 35.0
    general_agent_context_chars: int = 8500
    general_agent_max_plan_steps: int = 12
    general_agent_allow_internal_writes: bool = True
    workflow_max_steps: int = 30
    workflow_max_attempts: int = 3
    runtime_max_wall_seconds: float = 90.0
    runtime_max_tool_calls: int = 12
    memory_retention_days: int = 365
    knowledge_chunk_chars: int = 1200
    tool_timeout_seconds: float = 20.0

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: str | Path | None = None,
        base_dir: str | Path | None = None,
    ) -> "Settings":
        base = Path(base_dir) if base_dir else Path(__file__).resolve().parent.parent
        merged: dict[str, str] = {}
        merged.update(load_dotenv(Path(env_file) if env_file else base / ".env"))
        merged.update(os.environ if env is None else env)
        g = merged.get

        def path(name: str, default: str) -> Path:
            p = Path(g(name) or default)
            return p if p.is_absolute() else base / p

        ai_keys = {p: g(f"{p.upper()}_API_KEY", "") for p in PROVIDERS}
        ai_keys = {p: k for p, k in ai_keys.items() if k}
        default_provider = (g("AI_PROVIDER") or (next(iter(ai_keys), "anthropic"))).lower()
        if default_provider not in PROVIDERS:
            raise ConfigError(f"AI_PROVIDER must be one of {PROVIDERS}, got {default_provider!r}")

        base_urls = {
            "anthropic": g("ANTHROPIC_BASE_URL") or "https://api.anthropic.com",
            "openai": g("OPENAI_BASE_URL") or "https://api.openai.com/v1",
            "gemini": g("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta",
        }
        routes = cls._build_routes(g, default_provider, ai_keys)

        plan = dict(DEFAULT_WEEKLY_PLAN)
        for i, name in enumerate(("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")):
            if g(f"PLAN_{name}"):
                plan[i] = g(f"PLAN_{name}", "").strip()

        return cls(
            base_dir=base,
            api_id=_int(g("TELEGRAM_API_ID"), 0, "TELEGRAM_API_ID"),
            api_hash=g("TELEGRAM_API_HASH", ""),
            bot_token=g("TELEGRAM_BOT_TOKEN", ""),
            owner_id=_int(g("OWNER_TELEGRAM_ID"), 0, "OWNER_TELEGRAM_ID"),
            target_channel=g("TARGET_CHANNEL", ""),
            db_path=path("DB_PATH", "data/poem_agent.db"),
            backup_dir=path("BACKUP_DIR", "data/backups"),
            image_dir=path("IMAGE_DIR", "data/images"),
            session_dir=path("SESSION_DIR", "data/sessions"),
            log_dir=path("LOG_DIR", "logs"),
            log_level=(g("LOG_LEVEL") or "INFO").upper(),
            user_agent=g("HTTP_USER_AGENT") or "PoemAgent/1.0 (poetry channel assistant; set HTTP_USER_AGENT with your contact)",
            ai_default_provider=default_provider,
            ai_keys=ai_keys,
            ai_base_urls=base_urls,
            task_routes=routes,
            pexels_key=g("PEXELS_API_KEY", ""),
            unsplash_key=g("UNSPLASH_ACCESS_KEY", ""),
            image_daily_limit=_int(g("IMAGE_DAILY_LIMIT"), 10, "IMAGE_DAILY_LIMIT"),
            min_image_width=_int(g("MIN_IMAGE_WIDTH"), 800, "MIN_IMAGE_WIDTH"),
            min_image_height=_int(g("MIN_IMAGE_HEIGHT"), 500, "MIN_IMAGE_HEIGHT"),
            license_allow=_csv(g("IMAGE_LICENSE_ALLOW"), DEFAULT_LICENSE_ALLOW),
            license_block=_csv(g("IMAGE_LICENSE_BLOCK"), DEFAULT_LICENSE_BLOCK),
            image_ai_judge=_bool(g("IMAGE_AI_JUDGE"), True),
            scan_interval_minutes=_int(g("SCAN_INTERVAL_MINUTES"), 60, "SCAN_INTERVAL_MINUTES"),
            scan_batch_limit=_int(g("SCAN_BATCH_LIMIT"), 30, "SCAN_BATCH_LIMIT"),
            scan_delay_min=_float(g("SCAN_DELAY_MIN"), 5.0, "SCAN_DELAY_MIN"),
            scan_delay_max=_float(g("SCAN_DELAY_MAX"), 15.0, "SCAN_DELAY_MAX"),
            min_poem_chars=_int(g("MIN_POEM_CHARS"), 20, "MIN_POEM_CHARS"),
            max_poem_chars=_int(g("MAX_POEM_CHARS"), 1500, "MAX_POEM_CHARS"),
            allow_zawgyi=_bool(g("ALLOW_ZAWGYI"), False),
            generic_hashtags=GENERIC_HASHTAGS | frozenset(_csv(g("EXTRA_GENERIC_HASHTAGS"), ())),
            dup_similar=_float(g("DUP_SIMILAR"), 0.90, "DUP_SIMILAR"),
            dup_borderline=_float(g("DUP_BORDERLINE"), 0.80, "DUP_BORDERLINE"),
            timezone_offset_minutes=_int(g("TIMEZONE_OFFSET_MINUTES"), 390, "TIMEZONE_OFFSET_MINUTES"),
            post_times=g("POST_TIMES") or "09:00,19:00",
            queue_target=_int(g("QUEUE_TARGET"), 3, "QUEUE_TARGET"),
            max_batch=_int(g("MAX_BATCH"), 10, "MAX_BATCH"),
            stats_interval_hours=_int(g("STATS_INTERVAL_HOURS"), 6, "STATS_INTERVAL_HOURS"),
            show_source_link=_bool(g("SHOW_SOURCE_LINK"), False),
            weekly_plan=plan,
            general_agent_enabled=_bool(g("GENERAL_AGENT_ENABLED"), True),
            general_agent_max_calls=_bounded_int(g("GENERAL_AGENT_MAX_CALLS"), 3, "GENERAL_AGENT_MAX_CALLS", 1, 5),
            general_agent_timeout_seconds=_bounded_float(g("GENERAL_AGENT_TIMEOUT_SECONDS"), 35.0, "GENERAL_AGENT_TIMEOUT_SECONDS", 5.0, 90.0),
            general_agent_context_chars=_bounded_int(g("GENERAL_AGENT_CONTEXT_CHARS"), 8500, "GENERAL_AGENT_CONTEXT_CHARS", 1000, 30000),
            general_agent_max_plan_steps=_bounded_int(g("GENERAL_AGENT_MAX_PLAN_STEPS"), 12, "GENERAL_AGENT_MAX_PLAN_STEPS", 1, 20),
            general_agent_allow_internal_writes=_bool(g("GENERAL_AGENT_ALLOW_INTERNAL_WRITES"), True),
            workflow_max_steps=_bounded_int(g("WORKFLOW_MAX_STEPS"), 30, "WORKFLOW_MAX_STEPS", 1, 100),
            workflow_max_attempts=_bounded_int(g("WORKFLOW_MAX_ATTEMPTS"), 3, "WORKFLOW_MAX_ATTEMPTS", 1, 8),
            runtime_max_wall_seconds=_bounded_float(g("RUNTIME_MAX_WALL_SECONDS"), 90.0, "RUNTIME_MAX_WALL_SECONDS", 1.0, 600.0),
            runtime_max_tool_calls=_bounded_int(g("RUNTIME_MAX_TOOL_CALLS"), 12, "RUNTIME_MAX_TOOL_CALLS", 1, 60),
            memory_retention_days=_bounded_int(g("MEMORY_RETENTION_DAYS"), 365, "MEMORY_RETENTION_DAYS", 1, 3650),
            knowledge_chunk_chars=_bounded_int(g("KNOWLEDGE_CHUNK_CHARS"), 1200, "KNOWLEDGE_CHUNK_CHARS", 300, 8000),
            tool_timeout_seconds=_bounded_float(g("TOOL_TIMEOUT_SECONDS"), 20.0, "TOOL_TIMEOUT_SECONDS", 1.0, 120.0),
        )

    @staticmethod
    def _build_routes(g, default_provider: str, ai_keys: Mapping[str, str]) -> dict[str, tuple[tuple[str, str], ...]]:
        order = [default_provider] + [p for p in ai_keys if p != default_provider]
        routes: dict[str, tuple[tuple[str, str], ...]] = {}
        for task in AI_TASKS:
            override = g(f"AI_MODEL_{task.upper()}")
            if override:
                chain = []
                for item in override.split(","):
                    provider, _, model = item.strip().partition(":")
                    if provider not in PROVIDERS or not model:
                        raise ConfigError(f"AI_MODEL_{task.upper()} must look like provider:model, got {item!r}")
                    chain.append((provider, model))
                routes[task] = tuple(chain)
            else:
                tier = "light" if task in LIGHT_TASKS else "heavy"
                routes[task] = tuple((p, DEFAULT_MODELS[p][tier]) for p in order)
        return routes

    @property
    def post_time_list(self) -> list[tuple[int, int]]:
        from core.time_utils import parse_hhmm_list
        return parse_hhmm_list(self.post_times)

    def missing_required(self) -> list[str]:
        missing = []
        if not self.api_id:
            missing.append("TELEGRAM_API_ID")
        if not self.api_hash:
            missing.append("TELEGRAM_API_HASH")
        if not self.bot_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.owner_id:
            missing.append("OWNER_TELEGRAM_ID")
        if not self.target_channel:
            missing.append("TARGET_CHANNEL")
        if not self.ai_keys:
            missing.append("ANTHROPIC_API_KEY or OPENAI_API_KEY or GEMINI_API_KEY")
        if not self.post_time_list:
            missing.append("POST_TIMES (valid HH:MM list)")
        return missing

    def redacted(self) -> dict[str, object]:
        return {
            "target_channel": self.target_channel,
            "owner_id": "set" if self.owner_id else "MISSING",
            "bot_token": "set" if self.bot_token else "MISSING",
            "api_id/api_hash": "set" if self.api_id and self.api_hash else "MISSING",
            "ai_providers": sorted(self.ai_keys),
            "image_sources": ["wikimedia"] + (["pexels"] if self.pexels_key else []) + (["unsplash"] if self.unsplash_key else []),
            "post_times": self.post_times,
            "general_agent_enabled": self.general_agent_enabled,
            "general_agent_max_calls": self.general_agent_max_calls,
            "workflow_max_steps": self.workflow_max_steps,
            "db_path": str(self.db_path),
        }

    def ensure_dirs(self) -> None:
        for d in (self.db_path.parent, self.backup_dir, self.image_dir, self.session_dir, self.log_dir):
            d.mkdir(parents=True, exist_ok=True)
  

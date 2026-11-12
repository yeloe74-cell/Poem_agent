"""Runnable application wiring for the owner-controlled poetry workflow."""
from __future__ import annotations
import argparse
import asyncio
import logging
from config.settings import Settings
from storage.database import Database
from storage.repositories import Repositories
from security.owner_auth import OwnerAuth
from security.execution_guard import ExecutionGuard
from security.permissions import PermissionManager
from memory.memory_manager import MemoryManager
from poetry.collector import PoemCollector
from poetry.poem_analyzer import PoemAnalyzer
from poetry.poem_selector import PoemSelector
from core.agent import Agent
from channel.channel_manager import ChannelManager
from channel.post_manager import PostManager
from channel.scheduler import Scheduler


def _build_brain(settings):
    """Construct only adapters whose credentials are configured; offline use is valid."""
    from config.model_config import load_catalog
    from core.ai_brain import AIBrain, ProviderAdapter
    from core.model_router import ModelCandidate, ModelRouter
    configs = load_catalog()
    candidates, adapters = [], {}
    for item in configs:
        key = settings.provider_key(item.provider)
        if not key or item.provider not in {"openai", "anthropic"}:
            continue
        candidate = ModelCandidate(item.provider, item.name, item.capabilities,
                                   item.context_window, item.cost_per_1k,
                                   item.latency_score, .7, True)
        candidates.append(candidate)
        adapters[(item.provider, item.name)] = ProviderAdapter(item.provider, key, item.name)
    return AIBrain(ModelRouter(candidates), adapters) if candidates else None


def build_app():
    settings = Settings.load()
    logging.basicConfig(level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    database = Database(settings.database_path)
    database.initialize()
    repositories = Repositories(database)
    auth = OwnerAuth(settings.owner_id)
    permissions = PermissionManager(auth, ExecutionGuard())
    memory = MemoryManager(repositories)
    collector = PoemCollector(repositories)
    analyzer = PoemAnalyzer()
    selector = PoemSelector(repositories)
    agent = Agent(settings, repositories, permissions, memory, collector, analyzer,
                  selector, brain=_build_brain(settings))
    from telegram.bot import TelegramBot
    bot = TelegramBot(settings, agent)
    channels = ChannelManager(repositories, permissions, bot)
    posts = PostManager(repositories, auth)
    scheduler = Scheduler(repositories, channels)
    bot.attach_services(channels=channels, posts=posts, scheduler=scheduler)
    return settings, database, agent, bot, scheduler


async def run() -> None:
    parser = argparse.ArgumentParser(description="Intelligent AI Poem Channel Management Agent")
    parser.add_argument("--check", action="store_true", help="initialize storage and check configuration")
    parser.add_argument("--poll", action="store_true", help="start Telegram bot and scheduled publishing")
    args = parser.parse_args()
    settings, _database, _agent, bot, scheduler = build_app()
    if args.check:
        print(f"Database initialized; owner configured={bool(settings.owner_id)}; Telegram configured={bool(settings.telegram_token)}")
        return
    if not args.poll:
        print("Poem Agent ready. Set owner/token and run with --poll to connect Telegram.")
        return
    if not settings.owner_id or not settings.telegram_token:
        raise SystemExit("OWNER_TELEGRAM_ID and TELEGRAM_BOT_TOKEN are required for --poll")
    scheduler_task = asyncio.create_task(scheduler.run(), name="approved-post-scheduler")
    try:
        await bot.run()
    finally:
        scheduler.stop()
        scheduler_task.cancel()
        await asyncio.gather(scheduler_task, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(run())

"""Poem Agent application entry point."""
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


def build_app():
    settings = Settings.load()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db = Database(settings.database_path)
    db.initialize()
    repos = Repositories(db)
    auth = OwnerAuth(settings.owner_id)
    guard = ExecutionGuard()
    permissions = PermissionManager(auth, guard)
    memory = MemoryManager(repos)
    collector = PoemCollector(repos)
    analyzer = PoemAnalyzer()
    selector = PoemSelector(repos)
    agent = Agent(settings, repos, permissions, memory, collector, analyzer, selector)
    return settings, db, agent


async def run() -> None:
    parser = argparse.ArgumentParser(description="Poem channel management bot")
    parser.add_argument("--check", action="store_true", help="initialize storage and check configuration")
    parser.add_argument("--poll", action="store_true", help="start Telegram long polling")
    args = parser.parse_args()
    settings, db, agent = build_app()
    if args.check:
        print(f"Database initialized at {settings.database_path}; owner configured={bool(settings.owner_id)}")
        return
    if args.poll:
        if not settings.telegram_token:
            raise SystemExit("TELEGRAM_BOT_TOKEN is required for --poll")
        from telegram.bot import TelegramBot
        await TelegramBot(settings, agent).run()
        return
    print("Poem Agent ready. Configure --poll to connect Telegram.")


if __name__ == "__main__":
    asyncio.run(run())

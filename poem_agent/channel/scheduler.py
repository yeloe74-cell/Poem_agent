"""Polling scheduler publishes only approved, due drafts."""
import asyncio
from datetime import datetime, timezone


class Scheduler:
    def __init__(self, repositories, channel_manager, interval=20):
        self.repos, self.channels, self.interval = repositories, channel_manager, max(5, interval)
        self.running = False

    async def tick(self):
        due = self.repos.db.all("SELECT id,approved_by FROM drafts WHERE status='approved' AND scheduled_at<=CURRENT_TIMESTAMP ORDER BY scheduled_at LIMIT 20")
        results = []
        for row in due:
            try:
                results.append((row["id"], await self.channels.publish(row["approved_by"], row["id"], approved=True), None))
            except Exception as exc:
                self.repos.db.execute("UPDATE drafts SET status='failed' WHERE id=? AND status='approved'", (row["id"],))
                results.append((row["id"], None, str(exc)))
        return results

    async def run(self):
        self.running = True
        while self.running:
            await self.tick()
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False

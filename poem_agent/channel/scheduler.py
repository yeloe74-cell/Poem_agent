"""Persistent approved-post scheduler; never selects unapproved drafts."""
import asyncio
import logging


class Scheduler:
    def __init__(self, repositories, channel_manager, interval=20):
        self.repos, self.channels = repositories, channel_manager
        self.interval = max(5, int(interval))
        self.running = False
        self.logger = logging.getLogger(__name__)

    async def tick(self):
        due = self.repos.db.all("SELECT id,approved_by FROM drafts WHERE status='approved' AND scheduled_at IS NOT NULL AND scheduled_at<=CURRENT_TIMESTAMP ORDER BY scheduled_at LIMIT 20")
        results = []
        for row in due:
            try:
                message_id = await self.channels.publish(row["approved_by"], row["id"], approved=True)
                results.append((row["id"], message_id, None))
            except Exception as exc:
                self.logger.exception("Scheduled publication failed for %s", row["id"])
                self.repos.db.execute("UPDATE drafts SET status='failed' WHERE id=? AND status='approved'", (row["id"],))
                self.repos.audit(row["approved_by"], "scheduled_publish", row["id"], "failed")
                results.append((row["id"], None, str(exc)))
        return results

    async def run(self):
        self.running = True
        while self.running:
            await self.tick()
            await asyncio.sleep(self.interval)

    def stop(self):
        self.running = False

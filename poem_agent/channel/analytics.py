"""Minimal channel metrics based only on locally recorded publications."""
class Analytics:
    def __init__(self, repositories):
        self.repos = repositories

    def summary(self, channel_id):
        rows = self.repos.db.all("SELECT published_at FROM drafts WHERE channel_id=? AND status='published' ORDER BY published_at DESC LIMIT 1000", (str(channel_id),))
        return {"channel_id": str(channel_id), "published_count": len(rows),
                "latest_published_at": rows[0]["published_at"] if rows else None,
                "note": "Telegram engagement metrics are unavailable unless separately collected with permitted access."}

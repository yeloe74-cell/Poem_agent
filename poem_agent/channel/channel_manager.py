"""Channel service for destinations, drafts, approval, and publication history."""
import uuid


class ChannelManager:
    def __init__(self, repositories, permissions, telegram_client=None):
        self.repos, self.permissions, self.telegram = repositories, permissions, telegram_client

    def add_channel(self, actor_id, channel_id, title, role):
        self.permissions.authorize(actor_id, "channel_config", approved=True)
        self.repos.db.execute("INSERT OR REPLACE INTO channels(id,owner_id,title,role,enabled) VALUES(?,?,?,?,1)",
                              (str(channel_id), actor_id, title, role))
        self.repos.audit(actor_id, "channel_config", str(channel_id), "saved")

    def create_draft(self, actor_id, poem_id, channel_id, text):
        self.permissions.authorize(actor_id, "draft", approved=True)
        if not self.repos.db.one("SELECT id FROM poems WHERE id=?", (poem_id,)):
            raise KeyError("Unknown poem")
        if not self.repos.db.one("SELECT id FROM channels WHERE id=? AND enabled=1", (str(channel_id),)):
            raise KeyError("Unknown or disabled channel")
        ident = str(uuid.uuid4())
        self.repos.db.execute("INSERT INTO drafts(id,poem_id,channel_id,text,status) VALUES(?,?,?,?,?)",
                              (ident, poem_id, str(channel_id), text, "pending_approval"))
        return ident

    async def publish(self, actor_id, draft_id, approved=False):
        self.permissions.authorize(actor_id, "publish", approved)
        row = self.repos.db.one("SELECT * FROM drafts WHERE id=? AND status='approved'", (draft_id,))
        if not row:
            raise ValueError("Draft must be approved before publishing")
        if self.telegram is None:
            raise RuntimeError("Telegram publisher is not configured")
        message_id = await self.telegram.send_message(row["channel_id"], row["text"])
        if not message_id:
            raise RuntimeError("Platform did not return a message ID")
        self.repos.db.execute("UPDATE drafts SET status='published',platform_message_id=?,published_at=CURRENT_TIMESTAMP WHERE id=? AND status='approved'", (str(message_id), draft_id))
        self.repos.audit(actor_id, "publish", draft_id, "published")
        return str(message_id)

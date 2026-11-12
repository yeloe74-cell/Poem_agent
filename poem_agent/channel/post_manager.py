"""Owner-only draft state transitions and scheduling validation."""
from datetime import datetime, timezone


class PostManager:
    def __init__(self, repositories, owner_auth):
        self.repos, self.auth = repositories, owner_auth

    def approve(self, actor_id, draft_id):
        self.auth.require_owner(actor_id)
        changed = self.repos.db.execute("UPDATE drafts SET status='approved',approved_by=? WHERE id=? AND status='pending_approval'", (actor_id, draft_id))
        if not changed:
            raise ValueError("Draft is missing or not awaiting approval")
        self.repos.audit(actor_id, "approve_draft", draft_id, "approved")

    def reject(self, actor_id, draft_id):
        self.auth.require_owner(actor_id)
        changed = self.repos.db.execute("UPDATE drafts SET status='rejected',approved_by=? WHERE id=? AND status='pending_approval'", (actor_id, draft_id))
        if not changed:
            raise ValueError("Draft is not pending approval")
        self.repos.audit(actor_id, "reject_draft", draft_id, "rejected")

    def schedule(self, actor_id, draft_id, local_time):
        self.auth.require_owner(actor_id)
        try:
            due = datetime.strptime(local_time, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        except ValueError as exc:
            raise ValueError("အချိန်ကို YYYY-MM-DD HH:MM (UTC) ပုံ��ံရေးပါ။") from exc
        if due <= datetime.now(timezone.utc):
            raise ValueError("အနာဂတ်အချိန်ကို ရွေးပါ။")
        changed = self.repos.db.execute("UPDATE drafts SET status='approved',approved_by=?,scheduled_at=? WHERE id=? AND status='pending_approval'", (actor_id, due.strftime("%Y-%m-%d %H:%M:%S"), draft_id))
        if not changed:
            raise ValueError("Schedule လုပ်ရန် pending draft မရှိပါ")
        self.repos.audit(actor_id, "schedule_draft", draft_id, "approved_and_scheduled")

    def pending(self, limit=50):
        return [dict(row) for row in self.repos.db.all("SELECT * FROM drafts WHERE status='pending_approval' ORDER BY created_at LIMIT ?", (max(1, min(int(limit), 200)),))]

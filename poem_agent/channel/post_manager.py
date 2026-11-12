"""Post drafts remain inert until explicit owner approval."""
class PostManager:
    def __init__(self, repositories, owner_auth):
        self.repos, self.auth = repositories, owner_auth

    def approve(self, actor_id, draft_id):
        self.auth.require_owner(actor_id)
        row = self.repos.db.one("SELECT status FROM drafts WHERE id=?", (draft_id,))
        if not row or row["status"] != "pending_approval":
            raise ValueError("Draft is missing or not awaiting approval")
        self.repos.db.execute("UPDATE drafts SET status='approved',approved_by=? WHERE id=?", (actor_id, draft_id))
        self.repos.audit(actor_id, "approve_draft", draft_id, "approved")

    def reject(self, actor_id, draft_id):
        self.auth.require_owner(actor_id)
        changed = self.repos.db.execute("UPDATE drafts SET status='rejected',approved_by=? WHERE id=? AND status='pending_approval'", (actor_id, draft_id))
        if not changed:
            raise ValueError("Draft is not pending approval")
        self.repos.audit(actor_id, "reject_draft", draft_id, "rejected")

    def pending(self, limit=50):
        return [dict(row) for row in self.repos.db.all("SELECT * FROM drafts WHERE status='pending_approval' ORDER BY created_at LIMIT ?", (max(1, min(limit, 200)),))]

"""Explicit approval workflows for drafts and destructive operations."""
class Approval:
    def __init__(self, post_manager, owner_auth):
        self.posts, self.auth = post_manager, owner_auth

    def approve_draft(self, actor_id, draft_id):
        self.auth.require_owner(actor_id)
        self.posts.approve(actor_id, draft_id)
        return {"approved": True, "draft_id": draft_id}

    def confirm_destructive(self, actor_id, action, typed_confirmation, expected):
        self.auth.require_owner(actor_id)
        if action not in {"delete_poem", "delete_draft", "remove_channel"}:
            raise ValueError("Not a supported destructive action")
        if typed_confirmation != expected:
            raise PermissionError("Confirmation text does not match")
        return True

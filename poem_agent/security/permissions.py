"""Actor permissions plus mandatory owner gates for publishing and deletion."""
class PermissionManager:
    def __init__(self, owner_auth, guard):
        self.auth, self.guard = owner_auth, guard

    def authorize(self, actor_id, action, approved=False):
        self.auth.require_owner(actor_id)
        if action in {"publish", "delete", "schedule", "permissions"} and not approved:
            raise PermissionError(f"Explicit owner approval required for {action}")
        return True

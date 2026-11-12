"""Owner identity check; owner ID is required for sensitive operations."""
class OwnerAuth:
    def __init__(self, owner_id: int):
        self.owner_id = int(owner_id)

    def is_owner(self, actor_id: int) -> bool:
        return self.owner_id > 0 and int(actor_id) == self.owner_id

    def require_owner(self, actor_id: int):
        if not self.is_owner(actor_id):
            raise PermissionError("Owner authorization required")

"""User-client integration is intentionally disabled absent explicit MTProto setup."""
class UserClient:
    def __init__(self, session_path=None):
        self.session_path = session_path

    async def connect(self):
        raise RuntimeError("MTProto is optional and not enabled; use the Bot API with granted channel access")

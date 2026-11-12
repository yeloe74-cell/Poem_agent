"""Telegram text handlers produce structured requests; external content is not trusted."""
class TelegramHandlers:
    def __init__(self, agent):
        self.agent = agent

    async def on_text(self, user_id: int, text: str, chat_id=None):
        return await self.agent.handle(user_id, text, {"chat_id": chat_id})

    @staticmethod
    def status_text(state: str) -> str:
        labels = {"thinking": "စဉ်းစားနေပါတယ်", "searching": "ရှာဖွေနေပါတယ်",
                  "analyzing": "စစ်ဆေးနေပါတယ်", "error": "အမှားဖြစ်နေပါတယ်"}
        return labels.get(state, "အလုပ်လုပ်နေပါတယ်")

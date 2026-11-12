"""Telegram polling adapter; requires bot membership and owner authorization."""
from __future__ import annotations
import asyncio
import json
import urllib.parse
import urllib.request


class TelegramBot:
    def __init__(self, settings, agent):
        self.settings, self.agent = settings, agent
        self.offset = 0
        self.base = f"https://api.telegram.org/bot{settings.telegram_token}"

    async def _request(self, method, data=None):
        body = urllib.parse.urlencode(data or {}).encode()
        request = urllib.request.Request(f"{self.base}/{method}", data=body)
        def send():
            with urllib.request.urlopen(request, timeout=35) as response:
                result = json.loads(response.read())
            if not result.get("ok"):
                raise RuntimeError(f"Telegram API error for {method}")
            return result["result"]
        return await asyncio.to_thread(send)

    async def send_message(self, chat_id, text):
        result = await self._request("sendMessage", {"chat_id": chat_id, "text": text[:4000]})
        return result.get("message_id")

    async def run(self):
        while True:
            try:
                updates = await self._request("getUpdates", {"timeout": 25, "offset": self.offset,
                                                               "allowed_updates": '["message","channel_post"]'})
                for update in updates:
                    self.offset = update["update_id"] + 1
                    message = update.get("message")
                    if not message:
                        continue
                    sender = message.get("from", {})
                    chat = message.get("chat", {})
                    text = message.get("text", "")
                    try:
                        result = await self.agent.handle(int(sender.get("id", 0)), text,
                            {"chat_id": chat.get("id"), "poem": message.get("text", "")})
                        await self.send_message(chat.get("id"), result.get("message", "Done"))
                    except PermissionError:
                        await self.send_message(chat.get("id"), "ဒီ bot ကို အသုံးပြုခွင့်မရှိပါ။")
                    except Exception:
                        await self.send_message(chat.get("id"), "အမိန့်ကို လုပ်ဆောင်မရပါ။ ပြန်စမ်းကြည့်ပါ။")
            except Exception:
                await asyncio.sleep(3)

"""Telegram Bot API polling, owner command handling, and safe response delivery."""
from __future__ import annotations
import asyncio
import json
import logging
import urllib.parse
import urllib.request
from telegram.handlers import TelegramHandlers


class TelegramBot:
    def __init__(self, settings, agent):
        self.settings, self.agent = settings, agent
        self.offset = 0
        self.logger = logging.getLogger(__name__)
        self.base = f"https://api.telegram.org/bot{settings.telegram_token}"
        self.handlers = TelegramHandlers(agent)
        self.channels = self.posts = self.scheduler = None

    def attach_services(self, channels=None, posts=None, scheduler=None):
        self.channels, self.posts, self.scheduler = channels, posts, scheduler

    async def _request(self, method, data=None, timeout=35):
        body = urllib.parse.urlencode(data or {}).encode()
        request = urllib.request.Request(f"{self.base}/{method}", data=body,
                                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        def send():
            with urllib.request.urlopen(request, timeout=timeout) as response:
                result = json.loads(response.read())
            if not result.get("ok"):
                raise RuntimeError(f"Telegram API rejected {method}")
            return result["result"]
        return await asyncio.to_thread(send)

    async def send_message(self, chat_id, text):
        result = await self._request("sendMessage", {"chat_id": chat_id, "text": str(text)[:4000]})
        return result.get("message_id")

    async def _dispatch(self, message):
        sender, chat = message.get("from", {}), message.get("chat", {})
        actor_id, chat_id = int(sender.get("id", 0)), chat.get("id")
        text = message.get("text", "")
        if not text:
            return
        try:
            answer = await self.handlers.dispatch(actor_id, text, self, chat_id)
            if answer:
                await self.send_message(chat_id, answer)
        except PermissionError:
            await self.send_message(chat_id, "ဒီလုပ်ဆောင်ချက်ကို ပိုင်ရှင်သာ လုပ်ဆောင်နိုင်ပါတယ်။")
        except (ValueError, KeyError) as exc:
            await self.send_message(chat_id, f"မလုပ်ဆောင်နိုင်ပါ: {str(exc)[:500]}")
        except Exception:
            self.logger.exception("Telegram update failed")
            await self.send_message(chat_id, "လုပ်ဆောင်မှု မအောင်မြင်ပါ။ မှတ်တမ်းတင်ထားပြီး ပြန်စမ်းနိုင်ပါတယ်။")

    async def run(self):
        if not self.settings.telegram_token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        delay = 1
        while True:
            try:
                updates = await self._request("getUpdates", {"timeout": 25, "offset": self.offset,
                    "allowed_updates": '["message"]'}, timeout=35)
                delay = 1
                for update in updates:
                    self.offset = update["update_id"] + 1
                    if "message" in update:
                        await self._dispatch(update["message"])
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Telegram polling failed; backing off")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

"""Owner-verified Telegram commands for poem collection and publishing."""
from __future__ import annotations
from poetry.credit_manager import CreditManager


HELP = """ကဗျာစီမံခန့်ခွဲမှု:
/add <ကဗျာ> — မူရင်းစာသားအတိုင်းသိမ်းရန်
/analyze <ကဗျာ> — ခေါင်းစဉ်/ခံစားချက်ခွဲခြမ်���ရန်
/poems — သိမ်းထားသောကဗျာများ
/channel <id> <title> <destination|source> — channel ထည့်ရန်
/draft <channel_id> <poem_id> — ပိုင်ရှင်စစ်ဆေးရန် draft ပြင်ဆင်ရန်
/pending — အတည်ပြုရန်စောင့်နေသော draft များ
/approve <draft_id> — ပိုင်ရှင်က draft အတည်ပြုရန်
/publish <draft_id> — အတည်ပြုထားသော draft ထုတ်ဝေရန်
/schedule <draft_id> <YYYY-MM-DD HH:MM> — အတည်ပြုထားသော draft အချိန်ဇယားသတ်မှတ်ရန်
"""


class TelegramHandlers:
    def __init__(self, agent):
        self.agent = agent

    async def dispatch(self, user_id: int, text: str, bot, chat_id=None):
        command, _, payload = text.strip().partition(" ")
        command = command.casefold().split("@", 1)[0]
        if command in {"/start", "/help"}:
            return HELP
        if command == "/add":
            return await self._agent(user_id, "collect", payload, bot)
        if command == "/analyze":
            result = await self.agent.handle(user_id, "analyze", {"poem": payload})
            return self._render(result)
        if command == "/poems":
            rows = self.agent.repos.list_poems(25)
            return "သိမ်းထားသောကဗျာ မရှိသေးပါ။" if not rows else "\n".join(
                f"{row['id']} | {row['language']} | {(row.get('emotion') or 'unknown')} | {row['text'][:80].replace(chr(10), ' ')}" for row in rows)
        if command == "/channel":
            fields = payload.split(maxsplit=2)
            if len(fields) != 3 or fields[2] not in {"source", "destination"}:
                raise ValueError("အသုံးပြုပုံ: /channel <id> <title> <source|destination>")
            bot.channels.add_channel(user_id, fields[0], fields[1], fields[2])
            return "Channel ကို မှတ်တမ်းတင်ပြီးပါပြီ။ Bot သည် channel ထဲတွင် သင့်လျော်သော permission ရှိရပါမည်။"
        if command == "/draft":
            fields = payload.split(maxsplit=1)
            if len(fields) != 2:
                raise ValueError("အသုံးပြုပုံ: /draft <channel_id> <poem_id>")
            poem = self.agent.repos.db.one("SELECT * FROM poems WHERE id=?", (fields[1],))
            if not poem:
                raise KeyError("ကဗျာမတွေ့ပါ")
            credit = CreditManager().format(poem["author"], poem["source"])
            content = poem["text"] + ("\n\n" + credit if credit else "")
            draft_id = bot.channels.create_draft(user_id, poem["id"], fields[0], content)
            bot.posts.repos.audit(user_id, "create_draft", draft_id, "pending_approval")
            return f"Draft ပြင်ဆင်ပြီးပါပြီ။ ID: {draft_id}\nထုတ်ဝေမီ /approve {draft_id} လုပ်ပါ။"
        if command == "/pending":
            rows = bot.posts.pending()
            return "အတည်ပြုရန် draft မရှိပါ။" if not rows else "\n".join(
                f"{row['id']} | channel={row['channel_id']} | {row['text'][:100].replace(chr(10), ' ')}" for row in rows)
        if command == "/approve":
            if not payload.strip():
                raise ValueError("/approve <draft_id>")
            bot.posts.approve(user_id, payload.strip())
            return "Draft ကို အတည်ပြုပြီးပါပြီ။ ထုတ်ဝေရန် /publish <draft_id> ကို သီးခြားပေးပါ။"
        if command == "/publish":
            if not payload.strip():
                raise ValueError("/publish <draft_id>")
            message_id = await bot.channels.publish(user_id, payload.strip(), approved=True)
            return f"အတည်ပြုထားသော draft ကို ထုတ်ဝေပြီးပါပြီ။ Telegram message ID: {message_id}"
        if command == "/schedule":
            fields = payload.split(maxsplit=1)
            if len(fields) != 2:
                raise ValueError("/schedule <draft_id> <YYYY-MM-DD HH:MM>")
            bot.posts.schedule(user_id, fields[0], fields[1])
            return "Approved draft အချိန်ဇယားသတ်မှတ်ပြီးပါပြီ။ Scheduler အလုပ်လုပ်နေချိန်တွင် ထုတ်ဝေပါမည်။"
        if text.strip().startswith("/"):
            return "မသိသော command ဖြစ်ပါတယ်။ /help ���ိုကြည့်ပါ။"
        result = await self.agent.handle(user_id, text, {"chat_id": chat_id})
        return self._render(result)

    async def _agent(self, user_id, operation, payload, bot):
        if not payload.strip():
            raise ValueError("ကဗျာစာသားကို ထည့်ပါ။")
        result = await self.agent.handle(user_id, operation, {"poem": payload})
        poem = result.get("poem", {})
        return f"{result['message']}\nID: {poem.get('id', 'n/a')}\nEmotion: {poem.get('emotion', 'uncertain')}"

    @staticmethod
    def _render(result):
        analysis = result.get("analysis")
        if analysis:
            return (f"{result['message']}\nခံစားချက်: {analysis['emotion']}\n"
                    f"အကြောင်းအရာ: {', '.join(analysis['themes']) or 'မသေချာ'}\n"
                    f"ပုံစံ: {analysis['style']}\n{analysis['warning']}")
        return result.get("message", "ပြီးပါပြီ။")

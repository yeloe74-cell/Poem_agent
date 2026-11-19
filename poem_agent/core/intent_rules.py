
"""Fast, offline understanding of common Burmese owner phrases.

Rules cover the everyday commands so most messages cost no AI call and
approval can never be triggered by an ambiguous sentence. Anything the rules
do not recognise goes to the AI (see ai_brain.parse_owner_message).
"""
from __future__ import annotations

import re

from config.constants import TOPIC_WORDS
from core.models import Intent
from core.time_utils import burmese_digits_to_ascii, parse_clock_hint, parse_count

_LINK_RE = re.compile(r"(?:https?://)?t\.me/[\w+/\-]+|@[A-Za-z]\w{3,}")
_YES = ("ဟုတ်", "အတည်ပြု", "yes", "အိုကေ", "ok")
_NO = ("မလုပ်", "မဟုတ်", "no", "ပယ်ဖျက်", "မလိုဘူး")


def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def _topic(text: str) -> tuple[str, str] | None:
    for word, kv in TOPIC_WORDS.items():
        if word in text:
            return kv
    return None


def rule_intent(text: str, *, awaiting_confirm: bool = False) -> Intent | None:
    """Return an Intent for clear phrases, else None."""
    t = burmese_digits_to_ascii(text.strip())
    low = t.lower()
    if not t:
        return None

    def mk(name: str, params: dict | None = None, conf: float = 0.9) -> Intent:
        return Intent(name=name, params=params or {}, confidence=conf, source="rule")

    if awaiting_confirm:
        if _has(t, _NO) or _has(low, ("no",)):
            return mk("cancel_confirm")
        if _has(t, _YES) or _has(low, ("yes", "ok")):
            return mk("confirm")

    if low in ("/start", "/help", "help") or "ကူညီ" in t:
        return mk("help")

    link = _LINK_RE.search(t)
    if link:
        if _has(t, ("ဖယ်", "ဖျက်")) or "remove" in low:
            return mk("remove_source", {"link": link.group(0)})
        if _has(t, ("ထည့်", "ပေါင်း")) or "add" in low:
            return mk("add_source", {"link": link.group(0)})

    if "ဒီနေ့" in t and "မတင်" in t:
        return mk("skip_today")

    tomorrow = "နက်ဖြန်" in t
    if (tomorrow or "ဒီနေ့" in t) and _has(t, ("သိမ်း", "တင်", "ထား")) and "မတင်" not in t:
        params: dict = {"day_offset": 1 if tomorrow else 0}
        hint = parse_clock_hint(t)
        if hint:
            params["hour"], params["minute"] = hint
        return mk("schedule", params)

    if "မတင်" not in t and (_has(t, ("တင်လိုက်", "တင်ပေး", "တင်ပါ", "တင်မယ်")) or "approve" in low):
        return mk("approve", {"now": True} if _has(t, ("ချက်ချင်း", "အခုတင်", "အခုပဲတင်")) else {})

    if "ပုံ" in t and _has(t, ("မသုံးနဲ့", "မသုံးပါနဲ့", "မသုံးရ")):
        return mk("avoid_image_style", {"style": "current"})

    if "မကြိုက်" in t or "မတင်" in t or "ဖယ်လိုက်" in t:
        return mk("reject")

    if _has(t, ("နောက်တစ်ပုဒ်", "နောက်တစ်ခု", "နောက်ထပ်တစ်ပုဒ်")):
        return mk("next_poem")

    if "ပုံ" in t and _has(t, ("ပြောင်း", "အသစ်", "တခြား")):
        return mk("change_image")

    if _has(t, ("များနေပြီ", "များလွန်း", "များလှပြီ")):
        topic = _topic(t)
        if topic:
            return mk("too_many", {"kind": topic[0], "key": topic[1]})
        return None

    count = parse_count(t)
    if "ကဗျာ" in t and count and _has(t, ("ပြင်", "ပြ", "ရွေး", "ထုတ်")):
        params = {"count": count}
        topic = _topic(t)
        if topic and topic[0] == "category":
            params["category"] = topic[1]
        return mk("prepare_posts", params)

    if "source" in low and ("list" in low or "စာရင်း" in t):
        return mk("list_sources")
    if _has(t, ("အခြေအနေ",)) or "status" in low:
        return mk("status")
    if _has(t, ("စာရင်း", "ရလဒ်")) or _has(low, ("report", "performance", "views")):
        return mk("report")
    if "ခဏရပ်" in t or "pause" in low:
        return mk("pause_auto")
    if "ပြန်စ" in t or "resume" in low:
        return mk("resume_auto")
    return None
  

"""Burmese/English intent recognition using conservative keyword families."""
class ReasoningEngine:
    ACTIONS = {
        "publish": ("publish", "post", "တင်လိုက်", "တင်ပါ", "ထုတ်ဝေ"),
        "schedule": ("schedule", "tomorrow", "မနက်ဖြန်", "စီစဉ်"),
        "delete": ("delete", "remove", "ဖျက်", "ပယ်ဖျက်"),
        "collect": ("collect", "save", "သိမ်း", "စုဆောင်း"),
        "analyze": ("analyze", "classify", "သုံးသပ်", "ခွဲခြား"),
    }

    def classify(self, text: str) -> dict:
        low = text.casefold()
        kind = next((name for name, words in self.ACTIONS.items() if any(word in low for word in words)), "assist")
        language = "my" if any("\u1000" <= ch <= "\u109f" for ch in text) else "en"
        return {"kind": kind, "language": language,
                "approval_required": kind in {"publish", "schedule", "delete"},
                "constraints": ["preserve_poem", "treat_external_content_as_data"]}

    def clarification_needed(self, intent, context):
        if intent["kind"] in {"publish", "schedule"}:
            return not bool(context.get("channel_id") and context.get("draft_id"))
        if intent["kind"] == "delete":
            return not bool(context.get("target_id"))
        return False

"""Spider status text. Telegram message text cannot embed arbitrary animated GIFs."""
from enum import StrEnum


class ThinkingState(StrEnum):
    INITIALIZING = "INITIALIZING"
    THINKING = "THINKING"
    SEARCHING = "SEARCHING"
    ANALYZING = "ANALYZING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


LABELS = {
    ThinkingState.INITIALIZING: "စတင်ပြင်ဆင်နေပါတယ်",
    ThinkingState.THINKING: "စဉ်းစားနေပါတယ်",
    ThinkingState.SEARCHING: "ရှာဖွေနေပါတယ်",
    ThinkingState.ANALYZING: "စစ်ဆေးနေပါတယ်",
    ThinkingState.PLANNING: "အစီအစဉ်ဆွဲနေပါတယ်",
    ThinkingState.EXECUTING: "လုပ်ဆောင်နေပါတယ်",
    ThinkingState.COMPLETED: "ပြီးပါပြီ",
    ThinkingState.ERROR: "အမှားဖြစ်နေပါတယ်",
}


class ThinkingIndicator:
    """Render truthful text state; a sticker/GIF must be sent as a separate Telegram message."""
    def __init__(self, spider_emoji="🕷️"):
        self.spider_emoji = spider_emoji
        self.state = ThinkingState.INITIALIZING

    def set_state(self, state):
        self.state = ThinkingState(state)
        return self.render()

    def render(self):
        return f"{LABELS[self.state]} {self.spider_emoji}"

    @staticmethod
    def supports_inline_animation():
        return False

"""Shared constants: emotions, categories, keyword maps and defaults."""
from __future__ import annotations

# key -> Burmese label ---------------------------------------------------
EMOTIONS: dict[str, str] = {
    "longing": "အလွမ်း",
    "love": "အချစ်",
    "loneliness": "အထီးကျန်မှု",
    "sadness": "ဝမ်းနည်းမှု",
    "hope": "မျှော်လင့်ချက်",
    "joy": "ပျော်ရွှင်မှု",
    "anger": "ဒေါသ",
    "philosophy": "ဘဝအတွေးအခေါ်",
    "nostalgia": "လွမ်းဆွတ်မှု",
    "disappointment": "စိတ်ပျက်မှု",
    "remembrance": "သတိရခြင်း",
    "peace": "ငြိမ်းချမ်းမှု",
}

CATEGORIES: dict[str, str] = {
    "love_poetry": "အချစ်ကဗျာ",
    "sad_poetry": "ဝမ်းနည်းကဗျာ",
    "life_philosophy": "ဘဝအတွေးအခေါ်",
    "nature": "သဘာဝကဗျာ",
    "war_peace": "စစ်ပွဲနှင့် ငြိမ်းချမ်းရေး",
    "friendship": "မိတ်ဆွေကဗျာ",
    "motivation": "စိတ်ဓာတ်ခွန်အားကဗျာ",
    "romantic": "ရိုမန်းတစ်ကဗျာ",
    "dark": "မှောင်မိုက်ကဗျာ",
    "classical": "ရှေးရိုးကဗျာ",
    "short": "ကဗျာတို",
    "free_verse": "အလွတ်ကဗျာ",
}

# Plan-only pseudo category: "pick the best poems regardless of category".
BEST_CATEGORY = "best"
PLAN_LABELS: dict[str, str] = {**CATEGORIES, BEST_CATEGORY: "ရွေးချယ်ထားသော အကောင်းဆုံးကဗျာ", "any": "ကြိုက်ရာ"}

# Monday=0 ... Sunday=6 (matches the example in the project blueprint)
DEFAULT_WEEKLY_PLAN: dict[int, str] = {
    0: "love_poetry",
    1: "life_philosophy",
    2: "sad_poetry",
    3: "nature",
    4: "romantic",
    5: "classical",
    6: BEST_CATEGORY,
}

# Words the owner may use -> (kind, key). Substring matching.
TOPIC_WORDS: dict[str, tuple[str, str]] = {
    "အလွမ်း": ("emotion", "longing"),
    "အထီးကျန်": ("emotion", "loneliness"),
    "စိတ်ပျက်": ("emotion", "disappointment"),
    "ဒေါသ": ("emotion", "anger"),
    "ငြိမ်းချမ်း": ("emotion", "peace"),
    "မျှော်လင့်": ("emotion", "hope"),
    "သတိရ": ("emotion", "remembrance"),
    "အချစ်": ("category", "love_poetry"),
    "ဝမ်းနည်း": ("category", "sad_poetry"),
    "သဘာဝ": ("category", "nature"),
    "ရိုမန်း": ("category", "romantic"),
    "ဘဝ": ("category", "life_philosophy"),
    "ရှေးရိုး": ("category", "classical"),
    "ဂန္ထဝင်": ("category", "classical"),
}

# Fallback visual themes (English stock-photo queries) per emotion.
EMOTION_VISUALS: dict[str, list[str]] = {
    "longing": ["rainy window", "empty railway platform"],
    "love": ["sunset silhouette", "red flowers"],
    "loneliness": ["empty street night", "lonely bench"],
    "sadness": ["rain drops window", "grey cloudy sky"],
    "hope": ["sunrise horizon", "green sprout"],
    "joy": ["flower field sunlight", "blue sky birds"],
    "anger": ["storm clouds", "fire sparks"],
    "philosophy": ["mountain mist", "forest road"],
    "nostalgia": ["old photographs", "vintage street"],
    "disappointment": ["wilted flower", "empty room"],
    "remembrance": ["candle light", "old letters"],
    "peace": ["calm lake", "quiet temple morning"],
}

# Hashtags that are NOT a poet's name.
GENERIC_HASHTAGS: frozenset[str] = frozenset({
    "ကဗျာ", "ကဗျာများ", "ကဗျာလေး", "မြန်မာကဗျာ", "စာပေ", "poem", "poetry",
    "myanmarpoem", "burmesepoem", "quote", "quotes",
})

# Owner intents the agent can execute.
INTENTS: tuple[str, ...] = (
    "approve", "reject", "next_poem", "change_image", "avoid_image_style",
    "schedule", "skip_today", "prepare_posts", "too_many", "add_source",
    "remove_source", "list_sources", "status", "report", "pause_auto",
    "resume_auto", "set_plan", "help", "confirm", "cancel_confirm", "unknown",
)
# These always require an explicit owner confirmation first.
DESTRUCTIVE_INTENTS: frozenset[str] = frozenset({"remove_source"})

AVOID_COOLDOWN_DAYS = 3
TELEGRAM_CAPTION_LIMIT = 1024
TELEGRAM_TEXT_LIMIT = 4096


"""Conservative multilingual heuristic analysis; outputs must be reviewed."""
class PoemAnalyzer:
    TERMS = {
        "love": {"love", "heart", "ချစ်", "အချစ်"},
        "longing": {"miss", "memory", "လွမ်း", "သတိရ"},
        "nature": {"rain", "flower", "river", "sky", "မိုး", "ပန်း", "မြစ်"},
        "hope": {"hope", "dawn", "light", "မျှော်လင့်", "အလင်း"},
        "grief": {"loss", "tears", "sad", "ဝမ်းနည်း", "မျက်ရည်"},
    }

    def analyze(self, text: str, language="und") -> dict:
        if not text.strip():
            raise ValueError("Cannot analyze empty text")
        low = text.casefold()
        counts = {theme: sum(word in low for word in words) for theme, words in self.TERMS.items()}
        active = [key for key, count in counts.items() if count]
        emotion = max(counts, key=counts.get) if max(counts.values(), default=0) else "uncertain"
        lines = [line for line in text.splitlines() if line.strip()]
        words = low.split()
        diversity = len(set(words)) / max(1, len(words))
        return {"language": language, "emotion": emotion, "themes": active,
                "style": "free verse" if len(lines) > 1 and len({len(x) for x in lines}) > 1 else "undetermined",
                "quality": round(min(1.0, .35 + diversity * .35 + min(len(lines), 8) * .03), 3),
                "line_count": len(lines), "word_count": len(words), "confidence": .2,
                "author": None, "warning": "Heuristic only; author, meaning, and quality require human review."}

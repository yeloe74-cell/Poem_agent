"""Context keyword extraction and deterministic candidate ranking."""
class ImageMatcher:
    STOP = {"the", "and", "with", "from", "this", "that", "အတွက်", "သည်", "ကို", "၏"}

    def keywords(self, poem: str, emotion: str = "") -> str:
        tokens = [word.strip(".,!?;:()[]{}\"'“”၊။") for word in poem.split()]
        useful = [word for word in tokens if len(word) > 2 and word.casefold() not in self.STOP]
        mood = {"love": "romantic warm light", "longing": "quiet sunset rain",
                "nature": "nature flowers landscape", "hope": "dawn sunrise light",
                "grief": "rain solitude"}.get(emotion.casefold(), "")
        return " ".join((useful[:8] + ([mood] if mood else [])))

    def rank(self, poem: str, emotion: str, candidates: list[dict]):
        terms = set(self.keywords(poem, emotion).casefold().split())
        def score(item):
            description = " ".join(str(item.get(key, "")) for key in ("title", "creator", "attribution")).casefold()
            overlap = sum(term in description for term in terms)
            licensed = 1 if item.get("license") else 0
            return overlap + licensed * .25
        return sorted(candidates, key=score, reverse=True)

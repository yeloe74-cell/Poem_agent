"""Media discovery and matching orchestration with provider isolation."""
from media.image_sources import OpenverseSource
from media.image_matcher import ImageMatcher
from media.image_validator import ImageValidator


class ImageEngine:
    def __init__(self, sources=None, validator=None):
        self.sources = list(sources or [OpenverseSource()])
        self.validator = validator or ImageValidator()
        self.matcher = ImageMatcher()

    async def search_for_poem(self, poem: str, emotion: str = "", limit: int = 5):
        terms = self.matcher.keywords(poem, emotion)
        candidates = []
        for source in self.sources:
            try:
                rows = await source.search(terms, limit=limit)
                candidates.extend(rows)
            except Exception:
                continue
        ranked = self.matcher.rank(poem, emotion, candidates)
        return [item for item in ranked if self.validator.metadata_valid(item)][:limit]

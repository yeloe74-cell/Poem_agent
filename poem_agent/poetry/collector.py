"""Poem ingestion preserves text and reports duplicates without mutation."""
import hashlib
import uuid


class PoemCollector:
    def __init__(self, repositories):
        self.repositories = repositories

    @staticmethod
    def fingerprint(text: str) -> str:
        canonical = " ".join(text.casefold().split())
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def collect(self, text: str, language="und", author=None, source=None, analysis=None):
        if not text or not text.strip():
            raise ValueError("Poem must not be empty")
        analysis = analysis or {}
        record = {"id": str(uuid.uuid4()), "text": text, "fingerprint": self.fingerprint(text),
                  "language": language, "author": author, "source": source,
                  "emotion": analysis.get("emotion"), "themes": analysis.get("themes", []),
                  "style": analysis.get("style"), "quality": analysis.get("quality")}
        saved = self.repositories.add_poem(record)
        return {**record, "saved": saved, "duplicate": not saved}

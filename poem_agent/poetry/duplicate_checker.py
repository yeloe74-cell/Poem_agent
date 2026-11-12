"""Exact and near-duplicate checks, bounded to avoid unbounded scans."""
class DuplicateChecker:
    def __init__(self, repositories):
        self.repositories = repositories

    def exact(self, fingerprint: str):
        return self.repositories.db.one("SELECT id FROM poems WHERE fingerprint=?", (fingerprint,)) is not None

    def similar(self, text: str, threshold=.8, limit=500):
        tokens = set(" ".join(text.casefold().split()).split())
        found = []
        for row in self.repositories.db.all("SELECT id,text FROM poems ORDER BY created_at DESC LIMIT ?", (min(max(limit, 1), 1000),)):
            other = set(" ".join(row["text"].casefold().split()).split())
            similarity = len(tokens & other) / max(1, len(tokens | other))
            if similarity >= threshold:
                found.append((row["id"], similarity))
        return sorted(found, key=lambda pair: pair[1], reverse=True)

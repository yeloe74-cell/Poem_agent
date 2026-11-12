"""Persistent owner-scoped memory with provenance, correction, and deletion."""
import uuid


class MemoryManager:
    def __init__(self, repositories):
        self.repositories = repositories

    def remember(self, owner_id, kind, content, confidence=.7, source="owner", expires_at=None, verified=False):
        if not content.strip() or not 0 <= confidence <= 1:
            raise ValueError("Memory content and confidence are invalid")
        ident = str(uuid.uuid4())
        self.repositories.save_memory({"id": ident, "owner_id": owner_id, "kind": kind,
            "content": content, "confidence": confidence, "source": source,
            "expires_at": expires_at, "verified": verified})
        return ident

    def recall(self, owner_id, kind=None):
        return self.repositories.memories(owner_id, kind)

    def correct(self, owner_id, memory_id, content, source="owner correction"):
        row = self.repositories.db.one("SELECT id FROM memories WHERE id=? AND owner_id=?", (memory_id, owner_id))
        if not row:
            return False
        self.repositories.db.execute("UPDATE memories SET content=?,confidence=1,source=?,verified=1 WHERE id=? AND owner_id=?",
                                     (content, source, memory_id, owner_id))
        return True

    def forget(self, owner_id, memory_id):
        return bool(self.repositories.db.execute("DELETE FROM memories WHERE id=? AND owner_id=?", (memory_id, owner_id)))

    def semantic_candidates(self, owner_id, query, limit=8):
        terms = set(query.casefold().split())
        ranked = []
        for item in self.recall(owner_id):
            words = set(item["content"].casefold().split())
            score = len(terms & words) / max(1, len(terms | words))
            if score:
                ranked.append((score * item["confidence"], item))
        return [row for _, row in sorted(ranked, key=lambda pair: pair[0], reverse=True)[:max(1, limit)]]

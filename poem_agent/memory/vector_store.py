"""Optional vector memory with validated finite vectors and cosine retrieval."""
import math


class VectorStore:
    def __init__(self):
        self._records = {}

    def add(self, key, text, vector):
        if not key or not vector or any(not math.isfinite(float(x)) for x in vector):
            raise ValueError("Vector entry must have a key and finite values")
        self._records[key] = (text, [float(x) for x in vector])

    @staticmethod
    def cosine(left, right):
        if len(left) != len(right):
            return 0.0
        denom = math.sqrt(sum(x*x for x in left) * sum(y*y for y in right))
        return sum(x*y for x, y in zip(left, right)) / denom if denom else 0.0

    def search(self, vector, limit=5):
        scored = [(key, text, self.cosine(vector, stored)) for key, (text, stored) in self._records.items()]
        return sorted(scored, key=lambda row: row[2], reverse=True)[:max(0, min(limit, 100))]

    def delete(self, key):
        return self._records.pop(key, None) is not None

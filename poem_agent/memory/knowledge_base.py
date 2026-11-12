"""Knowledge facts include provenance and confidence instead of implicit certainty."""
class KnowledgeBase:
    def __init__(self):
        self._facts = {}

    def put(self, key, value, source, confidence=.5):
        if not source or not 0 <= confidence <= 1:
            raise ValueError("A source and valid confidence are required")
        self._facts[key] = {"value": value, "source": source, "confidence": confidence}

    def get(self, key):
        return self._facts.get(key)

    def delete(self, key):
        return self._facts.pop(key, None) is not None

    def search(self, query):
        term = query.casefold()
        return [(key, item) for key, item in self._facts.items()
                if term in key.casefold() or term in item["value"].casefold()]

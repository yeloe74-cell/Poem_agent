"""Research notes require explicit source provenance and confidence."""
class Research:
    def __init__(self, knowledge_base):
        self.knowledge = knowledge_base

    def add_source_note(self, topic, note, source, confidence=.5):
        if not source or not source.strip():
            raise ValueError("Research notes require a source")
        self.knowledge.put(topic, note, source, confidence)

    def find(self, topic):
        return self.knowledge.search(topic)

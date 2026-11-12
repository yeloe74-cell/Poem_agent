"""In-memory conversation context with strict bounded history."""
from collections import defaultdict, deque


class Conversation:
    def __init__(self, max_turns=12):
        self.turns = defaultdict(lambda: deque(maxlen=max(2, max_turns)))

    def add(self, user_id, role, text):
        if role not in {"user", "assistant"}:
            raise ValueError("unsupported conversation role")
        self.turns[int(user_id)].append({"role": role, "text": text[:4000]})

    def get(self, user_id):
        return list(self.turns[int(user_id)])

    def clear(self, user_id):
        self.turns.pop(int(user_id), None)

"""Model candidate scoring uses task fit, availability, context, cost, and latency."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCandidate:
    provider: str
    model: str
    capabilities: frozenset[str]
    context_window: int = 8192
    cost: float = 0.0
    latency: float = 1.0
    quality: float = .7
    available: bool = True


class ModelRouter:
    def __init__(self, candidates):
        self.candidates = list(candidates)
        self.failures = {}

    def choose(self, task, language="en", complexity=.4, context_tokens=0):
        required = {"general"}
        if task in {"reasoning", "planning", "coding"} or complexity >= .7:
            required.add("reasoning")
        if language == "my":
            required.add("burmese")
        eligible = [m for m in self.candidates if m.available and m.context_window >= context_tokens
                    and self.failures.get((m.provider, m.model), 0) < 3]
        if not eligible:
            return None
        def score(m):
            match = len(required & m.capabilities) / len(required)
            return match * 3 + m.quality - m.cost * (1 - complexity) - m.latency * .1
        return max(eligible, key=score)

    def record_failure(self, candidate):
        key = (candidate.provider, candidate.model)
        self.failures[key] = self.failures.get(key, 0) + 1

    def record_success(self, candidate):
        self.failures[(candidate.provider, candidate.model)] = 0

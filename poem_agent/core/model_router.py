"""Model candidates scored against capabilities, context, cost, quality, and latency."""
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

    def choose(self, task, language="en", complexity=.4, context_tokens=0, exclude=None):
        exclude = set(exclude or ())
        required = {"general"}
        if task in {"reasoning", "planning", "coding"} or complexity >= .7:
            required.add("reasoning")
        if language == "my":
            required.add("burmese")
        eligible = [model for model in self.candidates if model.available
                    and model.context_window >= context_tokens
                    and (model.provider, model.model) not in exclude
                    and self.failures.get((model.provider, model.model), 0) < 3]
        if not eligible:
            return None
        def score(model):
            coverage = len(required & model.capabilities) / len(required)
            quality = model.quality * 1.25
            context_fit = min(1.0, model.context_window / max(context_tokens, 1)) * .2
            cost_penalty = model.cost * (1 - complexity)
            latency_penalty = model.latency * .1
            return coverage * 3 + quality + context_fit - cost_penalty - latency_penalty
        return max(eligible, key=score)

    def record_failure(self, candidate):
        key = (candidate.provider, candidate.model)
        self.failures[key] = self.failures.get(key, 0) + 1

    def record_success(self, candidate):
        self.failures[(candidate.provider, candidate.model)] = 0

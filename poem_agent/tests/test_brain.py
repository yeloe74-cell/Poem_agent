from core.ai_brain import AIBrain, ProviderAdapter
from core.model_router import ModelCandidate, ModelRouter


class FakeAdapter:
    def __init__(self, result="ok", failure=None):
        self.result, self.failure = result, failure

    async def complete(self, prompt, system=""):
        if self.failure:
            raise self.failure
        return self.result


def test_router_prefers_capabilities_and_context():
    weak = ModelCandidate("a", "small", frozenset({"general"}), 1000, .1, 1, .5)
    strong = ModelCandidate("b", "reason", frozenset({"general", "reasoning", "burmese"}), 8000, .3, 1, .9)
    choice = ModelRouter([weak, strong]).choose("reasoning", "my", .9, 4000)
    assert choice == strong


def test_brain_uses_adapter_and_tracks_usage():
    import asyncio
    candidate = ModelCandidate("local", "mock", frozenset({"general"}))
    brain = AIBrain(ModelRouter([candidate]), {"local": FakeAdapter("answer")})
    assert asyncio.run(brain.complete("prompt")) == "answer"
    assert brain.usage[0]["ok"] is True

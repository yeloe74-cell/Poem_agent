"""Owner feedback memory; learning never changes authorization policy."""
class LearningManager:
    def __init__(self, memory):
        self.memory = memory

    def record_feedback(self, owner_id, text, kind="preference"):
        return self.memory.remember(owner_id, kind, text, .85, "explicit owner feedback", verified=True)

    def correct_feedback(self, owner_id, memory_id, correction):
        return self.memory.correct(owner_id, memory_id, correction)

    @staticmethod
    def can_change_permissions(*_args, **_kwargs):
        return False

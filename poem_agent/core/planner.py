"""Explicit workflow steps with tool names and verification conditions."""
class Planner:
    def create(self, intent):
        kind = intent["kind"]
        plans = {
            "collect": [("validate poem", "poetry.collect", "stored or duplicate reported")],
            "analyze": [("analyze original", "poetry.analyze", "uncertainty included")],
            "publish": [("select or load draft", "channel.draft", "draft exists"), ("request approval", "approval.request", "owner approved"), ("publish", "telegram.publish", "message ID saved")],
            "schedule": [("prepare draft", "channel.draft", "draft valid"), ("approve schedule", "approval.request", "approved date stored")],
            "delete": [("identify target", "channel.delete", "target confirmed"), ("confirm deletion", "approval.request", "owner confirmed")],
        }
        return [{"name": name, "tool": tool, "verify": verify} for name, tool, verify in plans.get(kind, [("clarify request", "agent.reply", "relevant reply")])]

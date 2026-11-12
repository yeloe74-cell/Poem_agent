"""Skill definitions are declarative; no downloaded code is executed."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    tool_names: tuple[str, ...]


class SkillManager:
    def __init__(self, tool_manager):
        self.tools = tool_manager
        self.skills = {}

    def register(self, skill: Skill):
        missing = set(skill.tool_names) - self.tools.tools.keys()
        if missing:
            raise ValueError(f"Skill references unknown tools: {sorted(missing)}")
        self.skills[skill.name] = skill

    def get(self, name):
        return self.skills.get(name)

    def available(self):
        return list(self.skills.values())

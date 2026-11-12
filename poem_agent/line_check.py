"""Run exact physical line count checks for designated modules."""
from pathlib import Path
import sys

TARGETS = ["main.py", "core/agent.py", "core/ai_brain.py", "core/model_router.py",
           "core/reasoning.py", "core/planner.py", "memory/memory_manager.py",
           "poetry/collector.py", "poetry/poem_analyzer.py", "media/image_engine.py",
           "channel/channel_manager.py", "telegram/bot.py", "storage/database.py",
           "tools/tool_manager.py", "security/execution_guard.py"]


def main():
    root = Path(__file__).resolve().parent
    errors = []
    for relative in TARGETS:
        path = root / relative
        if not path.is_file():
            errors.append(f"MISSING {relative}")
            continue
        count = len(path.read_text(encoding="utf-8").splitlines())
        print(f"{relative}: {count}")
        if not 301 <= count <= 399:
            errors.append(f"OUT OF RANGE {relative}: {count}")
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

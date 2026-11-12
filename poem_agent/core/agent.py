"""Intent parser and owner-controlled poem workflow; external text is always data."""
from __future__ import annotations
import uuid
from core.reasoning import ReasoningEngine
from core.planner import Planner
from core.evaluator import Evaluator


class Agent:
    def __init__(self, settings, repositories, permissions, memory, collector, analyzer,
                 selector, brain=None):
        self.settings, self.repos, self.permissions = settings, repositories, permissions
        self.memory, self.collector, self.analyzer, self.selector = memory, collector, analyzer, selector
        self.brain = brain
        self.reasoner, self.planner, self.evaluator = ReasoningEngine(), Planner(), Evaluator()

    async def handle(self, actor_id: int, text: str, context=None):
        self.permissions.authorize(actor_id, "interact", approved=True)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Message is empty")
        context = dict(context or {})
        intent = self.reasoner.classify(text)
        plan = self.planner.create(intent)
        task_id = str(uuid.uuid4())
        self.repos.db.execute("INSERT INTO tasks(id,owner_id,description,state,plan) VALUES(?,?,?,?,?)",
                              (task_id, actor_id, text[:4000], "PLANNING", self.evaluator.encode_plan(plan)))
        try:
            result = await self._execute(intent, actor_id, text, context)
            waiting = bool(result.get("approval_required"))
            verified = not waiting and self.evaluator.verify(result)
            state = "WAITING_FOR_APPROVAL" if waiting else ("COMPLETED" if verified else "FAILED")
            self.repos.db.execute("UPDATE tasks SET state=?,result=?,verified=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (state, result.get("message", "")[:4000], int(verified), task_id))
            return {"task_id": task_id, "status": state, **result, "plan": plan}
        except Exception as exc:
            self.repos.db.execute("UPDATE tasks SET state='FAILED',error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                                  (str(exc)[:1000], task_id))
            raise

    async def _execute(self, intent, actor_id, text, context):
        kind = intent["kind"]
        poem = context.get("poem")
        if kind == "collect":
            poem = poem if poem is not None else self._command_payload(text, ("collect", "save", "သိမ်း", "စုဆောင်း"))
            if not poem:
                return {"message": "ကဗျာစာသားကို သီးခြားပေးပို့ပါ၊ သို့မဟုတ် /add <ကဗျာစာသား> ကိုသုံးပါ။"}
            analysis = self.analyzer.analyze(poem, intent["language"])
            record = self.collector.collect(poem, intent["language"], context.get("author"), context.get("source"), analysis)
            return {"message": "ကဗျာကို သိမ်းဆည်းပြီးပါပြီ။" if record["saved"] else "ဒီကဗျာကို ယခင်က သိမ်းထားပြီးပါပြီ။", "poem": record}
        if kind == "analyze":
            poem = poem if poem is not None else self._command_payload(text, ("analyze", "classify", "သုံးသပ်", "ခွဲခြား"))
            if not poem:
                return {"message": "စစ်ဆေးလိုတဲ့ ကဗျာစာသားကို ပေးပို့ပါ။"}
            return {"message": "ကဗျာကို ခွဲခြမ်းစိတ်ဖြာပြီးပါပြီ။ အလိုအလျောက်သုံးသပ်ချက်ဖြစ်၍ ပြန်လည်စစ်ဆေးပါ။",
                    "analysis": self.analyzer.analyze(poem, intent["language"])}
        if kind in {"publish", "schedule", "delete"}:
            return {"message": "အရေးကြီးတဲ့လုပ်ဆောင်ချက်အတွက် draft/channel ကို ရွေးပြီး ပိုင်ရှင်အတည်ပြုချက်လိုအပ်ပါတယ်။ /help ကိုကြည့်ပါ။",
                    "approval_required": True}
        if self.brain and context.get("use_ai", True):
            try:
                from config.prompts import AGENT_SYSTEM
                answer = await self.brain.complete(text, task="general", language=intent["language"], system=AGENT_SYSTEM)
                if answer and answer.strip():
                    return {"message": answer.strip()[:4000]}
            except Exception:
                pass
        return {"message": "ကဗျာစုဆောင်းခြင်း၊ ခွဲခြမ်းစိတ်ဖြာခြင်း၊ ရွေးချယ်ခြင်းနှင့် အတည်ပြုချက်အပြီး channel သို့တင်ခြင်းကို ကူညီနိုင်ပါတယ်။ /help ကိုသုံးပါ။"}

    @staticmethod
    def _command_payload(text, markers):
        stripped = text.strip()
        for marker in markers:
            if stripped.casefold().startswith(marker.casefold()):
                return stripped[len(marker):].lstrip(" :၊-\n")
        return ""

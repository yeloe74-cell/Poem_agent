"""Intent parser, safe task planner, and owner-controlled poem workflow."""
from __future__ import annotations
import uuid
from core.reasoning import ReasoningEngine
from core.planner import Planner
from core.evaluator import Evaluator


class Agent:
    def __init__(self, settings, repositories, permissions, memory, collector, analyzer, selector):
        self.settings, self.repos, self.permissions = settings, repositories, permissions
        self.memory, self.collector, self.analyzer, self.selector = memory, collector, analyzer, selector
        self.reasoner, self.planner, self.evaluator = ReasoningEngine(), Planner(), Evaluator()

    async def handle(self, actor_id: int, text: str, context=None):
        self.permissions.authorize(actor_id, "interact", approved=True)
        if not text.strip():
            raise ValueError("Message is empty")
        intent = self.reasoner.classify(text)
        plan = self.planner.create(intent)
        task_id = str(uuid.uuid4())
        self.repos.db.execute("INSERT INTO tasks(id,owner_id,description,state,plan) VALUES(?,?,?,?,?)",
                              (task_id, actor_id, text, "PLANNING", self.evaluator.encode_plan(plan)))
        result = await self._execute(intent, actor_id, context or {})
        state = "WAITING_FOR_APPROVAL" if result.get("approval_required") else "COMPLETED"
        verified = self.evaluator.verify(result) if state == "COMPLETED" else False
        if state == "COMPLETED" and not verified:
            state = "FAILED"
        self.repos.db.execute("UPDATE tasks SET state=?,result=?,verified=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                              (state, result.get("message", ""), int(verified), task_id))
        return {"task_id": task_id, "status": state, **result, "plan": plan}

    async def _execute(self, intent, actor_id, context):
        if intent["kind"] == "collect":
            text = context.get("poem", "")
            if not text:
                return {"message": "ကဗျာစာသားကို ပေးပို့ပါ။"}
            analysis = self.analyzer.analyze(text, intent["language"])
            result = self.collector.collect(text, intent["language"], context.get("author"), context.get("source"), analysis)
            return {"message": "ကဗျာကို မှတ်တမ်းတင်ပြီးပါပြီ။" if result["saved"] else "ဒီကဗျာကို ယခင်က သိမ်းထားပြီးပါပြီ။", "poem": result}
        if intent["kind"] == "analyze":
            poem = context.get("poem", "")
            return {"message": "ကဗျာစာသားကို ပေးပို့ပါ။"} if not poem else {"message": "Analysis complete", "analysis": self.analyzer.analyze(poem, intent["language"])}
        if intent["kind"] in {"publish", "schedule", "delete"}:
            return {"message": "အတိအကျ draft နှင့် channel ကို ပြင်ဆင်ပြီးနောက် အတည်ပြုချက်တောင်းမည်။", "approval_required": True}
        return {"message": "ကဗျာစုဆောင်းခြင်း၊ ခွဲခြမ်းစိတ်ဖြာခြင်း၊ draft ပြင်ဆင်ခြင်းတို့ကို ကူညီနိုင်ပါတယ်။ လုပ်ဆောင်လိုသည့် channel နှင့် ကဗျာကို ပြောပြပါ။"}

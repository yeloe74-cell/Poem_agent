"""Completion and result validation helpers."""
import json


class Evaluator:
    @staticmethod
    def verify(result):
        if not isinstance(result, dict) or not isinstance(result.get("message"), str):
            return False
        if result.get("approval_required"):
            return False
        return bool(result["message"].strip())

    @staticmethod
    def encode_plan(plan):
        return json.dumps(plan, ensure_ascii=False)

    @staticmethod
    def verify_publication(message_id, approved):
        return bool(approved and isinstance(message_id, (str, int)) and str(message_id).strip())

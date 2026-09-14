"""Application layer for the Django API; views contain no ERP access logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any

import db_adapter
from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request, data_router
from intelligence.response_generator import generate_response
from rag.retriever import retrieve_policy


@dataclass(frozen=True)
class Identity:
    user_id: str
    role: str


class VoxERPService:
    def __init__(self, engine: IntentEngine | None = None):
        self.engine = engine or IntentEngine()

    def query(self, identity: Identity, text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if not text:
            return {"reply_text": "I didn't catch that, try again.", "status": 400}
        intent = self.engine.parse(text, identity.role, _schema_map())
        filters = intent.get("filters") or {}
        if intent.get("action") == "write" and intent.get("table") == "attendance" and not filters.get("subject"):
            return {"reply_text": "Which subject should I mark attendance for?", "status": 200}
        authorization = authorize_request(identity.user_id, identity.role, intent, text)
        if not authorization.get("allowed"):
            return {"reply_text": generate_response(authorization), "status": 200}
        if data_router.route(intent, text) == "rag":
            return {"reply_text": generate_response({"policy_context": retrieve_policy(identity.role, text)}), "status": 200}
        if intent.get("action") == "write":
            return self._pending(identity, authorization, filters)
        return self._read(authorization["target_student_id"], intent)

    def _read(self, student_id: str, intent: dict[str, Any]) -> dict[str, Any]:
        filters, table = intent["filters"], intent["table"]
        if table == "attendance":
            if not filters.get("subject"):
                return {"reply_text": "Which subject would you like attendance for?", "status": 200}
            result = db_adapter.get_attendance(student_id, filters["subject"])
        elif table == "marks":
            result = db_adapter.get_marks(student_id, filters.get("subject"))
        elif table == "timetable":
            result = db_adapter.get_timetable(student_id)
        else:
            return {"reply_text": "I can't help with that request.", "status": 200}
        return {"reply_text": generate_response(result), "status": 200}
    def _pending(self, identity: Identity, auth: dict[str, Any], filters: dict[str, Any]) -> dict[str, Any]:
        period = filters.get("period")
        if not isinstance(period, int) or not 1 <= period <= 10:
            return {"reply_text": "Please specify a valid attendance period from 1 to 10.", "status": 200}
        pending = {"student_id": auth["target_student_id"], "subject": filters["subject"], "date": filters.get("date") or date.today().isoformat(), "status": filters.get("status") or "absent", "period": period}
        return {"reply_text": f"Mark you {pending['status']} in {pending['subject']}, period {period} for today. Say yes or no.", "pending": pending, "requires_confirmation": True, "status": 200}

    def confirm(self, identity: Identity, pending: dict[str, Any], decision: str) -> dict[str, Any]:
        if decision != "yes":
            return {"reply_text": "Okay, no changes made.", "status": 200}
        required = {"student_id", "subject", "date", "status", "period"}
        if not isinstance(pending, dict) or not required.issubset(pending):
            return {"reply_text": "I lost track of that request, please try again.", "status": 400}
        period = pending["period"]
        if not isinstance(period, int) or not 1 <= period <= 10:
            return {"reply_text": "I couldn't verify the attendance period.", "status": 400}
        intent = {"action": "write", "table": "attendance", "filters": {**pending, "student_name": None}}
        auth = authorize_request(identity.user_id, identity.role, intent, f"mark {pending['student_id']} {pending['status']} in {pending['subject']}")
        if not auth.get("allowed") or auth.get("target_student_id") != pending["student_id"]:
            return {"reply_text": "You are not authorized to make that change.", "status": 403}
        result = db_adapter.mark_attendance(pending["student_id"], pending["subject"], pending["date"], pending["status"], actor_id=identity.user_id, period=period)
        return {"reply_text": generate_response(result), "status": 200}


@lru_cache(maxsize=1)
def _schema_map() -> dict[str, Any]:
    """Avoid rediscovering the stable ERP schema on every web request."""
    return db_adapter.build_schema_map()

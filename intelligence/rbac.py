import sqlite3
from typing import Any, Dict, Optional

from db_adapter import _connect


def authorize_request(user_id: str, role: str, intent: Dict[str, Any], text: str = "") -> Dict[str, Any]:
    """Return a structured authorization decision before any adapter call."""

    if not user_id or not isinstance(user_id, str):
        return {"allowed": False, "reason": "missing_user", "message": "I couldn't identify the current user."}

    normalized_role = (role or "").strip().lower() if isinstance(role, str) else ""
    if normalized_role not in {"student", "teacher"}:
        return {"allowed": False, "reason": "invalid_role", "message": "I couldn't determine the user's role."}

    if not isinstance(intent, dict):
        return {"allowed": False, "reason": "invalid_intent", "message": "I couldn't understand that request."}

    action = intent.get("action")
    table = intent.get("table")
    filters = intent.get("filters") or {}

    if action == "unsupported" or table == "unsupported":
        return {"allowed": False, "reason": "unsupported", "message": "I can't help with that request."}

    if normalized_role == "student":
        target_student_id = _resolve_target_student_id(filters)
        self_reference = _is_self_reference(text or "")

        if target_student_id is None:
            if _mentions_other_student(text or ""):
                return {"allowed": False, "reason": "unauthorized_target", "message": "You can only access your own data."}
            if self_reference:
                target_student_id = user_id
            else:
                return {"allowed": False, "reason": "ambiguous_target", "message": "I couldn't safely determine which student you meant."}

        if target_student_id != user_id:
            return {"allowed": False, "reason": "unauthorized_target", "message": "You can only access your own data."}

        if action == "write" and table == "attendance":
            return {"allowed": True, "reason": None, "message": None, "target_student_id": target_student_id}

        return {"allowed": True, "reason": None, "message": None, "target_student_id": target_student_id}

    if normalized_role == "teacher":
        target_student_id = _resolve_target_student_id(filters)
        if target_student_id is None:
            target_student_id = user_id

        if _teacher_permitted_class(user_id) is None:
            return {
                "allowed": False,
                "reason": "teacher_scope_unknown",
                "message": "The current database does not define teacher class membership, so access is blocked safely.",
            }

        student_class = _student_class(target_student_id)
        if student_class is None:
            return {"allowed": False, "reason": "unknown_student", "message": "I couldn't find that student."}

        return {"allowed": True, "reason": None, "message": None, "target_student_id": target_student_id}

    return {"allowed": False, "reason": "invalid_role", "message": "I couldn't determine the user's role."}


def _is_self_reference(text: str) -> bool:
    lowered = (text or "").lower()
    if _mentions_other_student(text):
        return False

    explicit_self_patterns = [
        " my ",
        "myself",
        " my marks",
        " my attendance",
        " my timetable",
        "show me my",
        "show me myself",
        "me my",
    ]
    return any(token in lowered for token in explicit_self_patterns)


def _mentions_other_student(text: str) -> bool:
    lowered = (text or "").lower()
    return any(token in lowered for token in [
        "another student",
        "another person's",
        "someone else's",
        "another person's attendance",
        "another student's marks",
        "another student's attendance",
        "someone else's marks",
        "someone else's attendance",
    ])


def _resolve_target_student_id(filters: Dict[str, Any]) -> Optional[str]:
    student_id = filters.get("student_id")
    if isinstance(student_id, str) and student_id.strip():
        return student_id.strip()

    student_name = filters.get("student_name")
    if isinstance(student_name, str) and student_name.strip():
        return _student_id_from_name(student_name.strip())

    return None


def _student_id_from_name(name: str) -> Optional[str]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM students WHERE lower(name) = lower(?)",
            (name,),
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def _student_class(student_id: str) -> Optional[str]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT class_name FROM students WHERE id = ?",
            (student_id,),
        ).fetchone()
        return row["class_name"] if row else None
    finally:
        conn.close()


def _teacher_permitted_class(user_id: str) -> Optional[str]:
    """The current database does not define a teacher-to-class relationship."""

    return None


__all__ = ["authorize_request"]
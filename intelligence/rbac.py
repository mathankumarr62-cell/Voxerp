from typing import Any, Dict, Optional

import db_adapter
from rag.retriever import retrieve_policy


class PolicyEngine:
    """Retrieve policy context; it never makes the final authorization decision."""

    def evaluate(self, role: str, text: str = "") -> Dict[str, Any]:
        policy_context = retrieve_policy(role, text)
        return {
            "policy_context": policy_context,
            "has_policy": bool(policy_context.strip()),
        }


class DataRouter:
    """Choose the source for a request: structured SQL data or RAG knowledge."""

    RAG_KEYWORDS = {
        "policy", "policies", "regulation", "regulations", "rule", "rules",
        "syllabus", "faq", "guideline", "guidelines", "document", "documents",
        "procedure", "procedures",
    }
    SQL_TABLES = {"students", "marks", "attendance", "timetable", "exams"}

    def route(self, intent: Dict[str, Any], text: str = "") -> str:
        """
        Select the data source without allowing an academic-table
        classification to override an explicit policy request.

        Priority:
        1. Explicit policy intent.
        2. Explicit policy/rule language in the user's request.
        3. Known SQL table.
        4. Safe default to SQL for supported structured-data requests.
        """
        table = intent.get("table") if isinstance(intent, dict) else None

        if table == "policy":
            return "rag"

        lowered = (text or "").strip().lower()

        if any(keyword in lowered for keyword in self.RAG_KEYWORDS):
            return "rag"

        if table in self.SQL_TABLES:
            return "sql"

        return "sql"


policy_engine = PolicyEngine()
data_router = DataRouter()


def authorize_request(user_id: str, role: str, intent: Dict[str, Any], text: str = "") -> Dict[str, Any]:
    """Return a structured authorization decision before any adapter call."""
    # Policy Engine retrieves context; deterministic RBAC remains authoritative.
    policy_result = policy_engine.evaluate(role, text)
    policy_context = policy_result["policy_context"]
    data_source = data_router.route(intent, text)
    _ = (policy_context, data_source)
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

    if action == "policy_query":
        if table != "policy":
            return {
                "allowed": False,
                "reason": "invalid_intent",
                "message": "I couldn't understand that request.",
            }

        # RAG/policy retrieval must never bypass deterministic RBAC.
        # A student explicitly referring to another student must be denied.
        if normalized_role == "student":
            target_student_id = _resolve_target_student_id(filters)

            if target_student_id is not None and target_student_id != user_id:
                return {
                    "allowed": False,
                    "reason": "unauthorized_target",
                    "message": "You can only access your own data.",
                    "target_student_id": target_student_id,
                }

            if _mentions_other_student(text or ""):
                return {
                    "allowed": False,
                    "reason": "unauthorized_target",
                    "message": "You can only access your own data.",
                    "target_student_id": None,
                }

        # Policy questions without another-student targeting are safe.
        # RAG supplies knowledge context only; it does not grant SQL access.
        return {
            "allowed": True,
            "reason": None,
            "message": None,
            "target_student_id": None,
        }
    if normalized_role == "student":
        target_student_id = _resolve_target_student_id(filters)
        self_reference = _is_self_reference(text or "")

        if target_student_id is None:
            lowered_text = (text or "").lower()
            if "another student" in lowered_text or "another student's" in lowered_text:
                return {"allowed": False, "reason": "unauthorized_target", "message": "You can only access your own data."}
            if _mentions_other_student(text or ""):
                return {"allowed": False, "reason": "ambiguous_target", "message": "I couldn't safely determine which student you meant."}
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
        # Never treat the teacher's ID as a student ID.
        target_student_id = _resolve_target_student_id(filters)

        # No student was specified.
        # Fail closed as ambiguous.
        if target_student_id is None:
            return {
                "allowed": False,
                "reason": "ambiguous_target",
                "message": "I couldn't safely determine which student you meant.",
            }

        # Find the teacher's assigned class.
        permitted_class = _teacher_permitted_class(user_id)

        # No class assignment = fail closed.
        if permitted_class is None:
            return {
                "allowed": False,
                "reason": "teacher_scope_unknown",
                "message": (
                    "The current database does not define teacher "
                    "class membership, so access is blocked safely."
                ),
            }

        # Check that requested student exists.
        student_class = _student_class(target_student_id)

        if student_class is None:
            return {
                "allowed": False,
                "reason": "unknown_student",
                "message": "I couldn't find that student.",
            }

        # Check teacher's class scope.
        if student_class != permitted_class:
            return {
                "allowed": False,
                "reason": "unauthorized_target",
                "message": "That student is outside your permitted class.",
            }

        # Teacher is authorized.
        return {
            "allowed": True,
            "reason": None,
            "message": None,
            "target_student_id": target_student_id,
        }

    return {"allowed": False, "reason": "invalid_role", "message": "I couldn't determine the user's role."}


def _is_self_reference(text: str) -> bool:
    lowered = (text or "").lower()

    # Explicit references to another person/student always take priority.
    if _mentions_other_student(text):
        return False

    explicit_self_patterns = [
        # Possessive/self references.
        " my ",
        "myself",
        " my marks",
        " my scores",
        " my results",
        " my attendance",
        " my timetable",
        "show me my",
        "show me myself",
        "me my",

        # Explicit self-targeted write references.
        # Keep this bounded to attendance/write-style commands so a generic
        # occurrence of "me" is never treated as authorization by itself.
        "mark me",
        "record me",
        "set me",
        "update me",

        # First-person references.
        " i ",
        " i scored",
        " i score",
        " i got",
        " i received",
        " i obtained",
        " what did i get",
        "what did i score",
        "how much did i score",
        "how much did i get",
    ]

    padded = f" {lowered} "
    return any(pattern in padded for pattern in explicit_self_patterns)


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
        "the student's",
        "the student",
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
    result = db_adapter.lookup_student(name=name)
    if result.get("status") == "ok" and result.get("student"):
        return result["student"].get("id")
    return None


def _student_class(student_id: str) -> Optional[str]:
    result = db_adapter.lookup_student(student_id=student_id)
    if result.get("status") == "ok" and result.get("student"):
        return result["student"].get("class_name")
    return None


def _teacher_permitted_class(user_id: str) -> Optional[str]:
    """Return a verified teacher class, or None when scope is unavailable.

    The current MariaDB schema does not define a teacher-to-class mapping,
    so teacher access must fail closed rather than guessing a class.
    """
    return None


__all__ = ["authorize_request", "PolicyEngine", "DataRouter", "policy_engine", "data_router"]

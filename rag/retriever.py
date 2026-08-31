from pathlib import Path
from typing import List


POLICY_DIR = Path(__file__).resolve().parent / "policy_documents"


def _load_policy(filename: str) -> str:
    path = POLICY_DIR / filename

    if not path.is_file():
        return ""

    return path.read_text(encoding="utf-8")


def retrieve_policy(role: str, query: str = "") -> str:
    """
    Retrieve the most relevant VoxERP authorization policies.

    RAG provides policy context only.
    Deterministic RBAC remains responsible for the final
    authorization decision.
    """

    role = (role or "").strip().lower()
    query = (query or "").strip().lower()

    policies: List[str] = []

    if role == "student":
        policy = _load_policy("student_policy.txt")
        if policy:
            policies.append(policy)

    elif role == "teacher":
        policy = _load_policy("teacher_policy.txt")
        if policy:
            policies.append(policy)

    # Attendance-specific policy
    if "attendance" in query or "absent" in query or "present" in query:
        policy = _load_policy("attendance_policy.txt")
        if policy:
            policies.append(policy)

    return "\n\n--- POLICY ---\n\n".join(policies)


__all__ = ["retrieve_policy"]

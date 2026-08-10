from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional

from google import genai


MODEL_NAME = "gemini-3.6-flash"

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["read", "write", "unsupported"],
            "description": "The operation requested by the user.",
        },
        "table": {
            "type": "string",
            "enum": ["attendance", "marks", "timetable", "unsupported"],
            "description": "The ERP table relevant to the request.",
        },
        "filters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": ["string", "null"],
                    "description": "Student ID if explicitly identifiable.",
                },
                "student_name": {
                    "type": ["string", "null"],
                    "description": "Student name if explicitly mentioned.",
                },
                "subject": {
                    "type": ["string", "null"],
                    "description": "Subject name if mentioned.",
                },
                "date": {
                    "type": ["string", "null"],
                    "description": "Date if explicitly mentioned.",
                },
                "status": {
                    "type": ["string", "null"],
                    "description": "Attendance status such as absent or present.",
                },
            },
            "required": [
                "student_id",
                "student_name",
                "subject",
                "date",
                "status",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["action", "table", "filters"],
    "additionalProperties": False,
}


class IntentEngine:
    """Convert natural-language VoxERP queries into structured intents."""

    def __init__(self, client: genai.Client | None = None) -> None:
        self.client = client
        if self.client is None:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                for env_path in [os.path.expanduser("~/.env"), os.path.join(os.path.dirname(__file__), "..", ".env")]:
                    if os.path.isfile(env_path):
                        try:
                            with open(env_path, "r") as f:
                                for line in f:
                                    line = line.strip()
                                    if line.startswith("GEMINI_API_KEY="):
                                        api_key = line.split("=", 1)[1].strip("'\" ")
                                        break
                        except Exception:
                            pass
                    if api_key:
                        break
            if api_key:
                try:
                    self.client = genai.Client(api_key=api_key)
                except Exception:
                    self.client = None
            else:
                self.client = None

    def parse(
        self,
        text: str,
        role: str,
        schema_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse a user query into the agreed VoxERP intent shape."""

        if not isinstance(text, str) or not text.strip():
            return self._fallback_intent()

        normalized_role = role.strip().lower() if isinstance(role, str) else ""
        if normalized_role not in {"student", "teacher"}:
            return self._fallback_intent()

        prompt = self._build_prompt(
            text=text.strip(),
            role=normalized_role,
            schema_map=schema_map,
        )

        if self.client is None:
            return self._fallback_intent()

        try:
            response = self.client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": INTENT_SCHEMA,
                    "system_instruction": (
                        "You are the VoxERP intent classification engine. "
                        "Classify the user's request only within the supported "
                        "ERP operations. Never invent database tables or fields. "
                        "Do not make authorization decisions; RBAC is handled "
                        "separately after intent classification."
                    ),
                },
            )

            if not getattr(response, "text", None):
                return self._fallback_intent()

            parsed = json.loads(response.text)
            return self._validate_intent(parsed)

        except Exception:
            return self._fallback_intent()

    @staticmethod
    def _build_prompt(
        text: str,
        role: str,
        schema_map: Dict[str, Any],
    ) -> str:
        schema_description = json.dumps(
            schema_map,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return f"""
VoxERP supports only these operations:

READ:
- attendance
- marks
- timetable

WRITE:
- mark attendance

The current user's role is: {role}

Database schema:
{schema_description}

User's spoken request:
{text}

Classification rules:

1. "attendance" queries belong to the attendance table.
2. "marks", "scores", "exam marks", or similar queries belong to the marks table.
3. Timetable or class-schedule queries belong to the timetable table.
4. A request to mark a student present/absent is a write operation on attendance.
5. If the request is unrelated to VoxERP's supported operations, classify it as unsupported.
6. Extract a student name only when the user explicitly mentions one.
7. Extract a student ID only when the user explicitly provides one.
8. Extract the subject exactly as spoken, without inventing a subject.
9. Extract a date only when the user explicitly gives one.
10. For attendance writes, extract the requested status such as "absent" or "present".
11. Do not decide whether the user is authorized to access another student. RBAC handles that separately.
12. Do not invent missing filters.
13. If the user says "my", "me", or "myself", do not treat that as a different student target; it is only a self-reference.
14. If the request mentions a timetable, class schedule, or timetable-related phrase, classify it as the timetable table even if it also mentions the word "my".
15. If the request is ambiguous, keep the relevant filters as null and do not guess a target student.
""".strip()

    @staticmethod
    def _validate_intent(intent: Any) -> Dict[str, Any]:
        """Validate and normalize the model's structured result."""

        if not isinstance(intent, dict):
            return IntentEngine._fallback_intent()

        action = intent.get("action")
        table = intent.get("table")
        filters = intent.get("filters")

        if action not in {"read", "write", "unsupported"}:
            return IntentEngine._fallback_intent()

        if table not in {
            "attendance",
            "marks",
            "timetable",
            "unsupported",
        }:
            return IntentEngine._fallback_intent()

        if not isinstance(filters, dict):
            return IntentEngine._fallback_intent()

        allowed_filters = {
            "student_id",
            "student_name",
            "subject",
            "date",
            "status",
        }

        cleaned_filters = {
            key: filters.get(key)
            for key in allowed_filters
        }

        return {
            "action": action,
            "table": table,
            "filters": cleaned_filters,
        }

    @staticmethod
    def _fallback_intent() -> Dict[str, Any]:
        """Safe fallback when intent classification fails."""

        return {
            "action": "unsupported",
            "table": "unsupported",
            "filters": {
                "student_id": None,
                "student_name": None,
                "subject": None,
                "date": None,
                "status": None,
            },
        }
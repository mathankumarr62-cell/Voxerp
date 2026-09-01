from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from google import genai


MODEL_NAME = "gemini-3.6-flash"


INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["read", "write", "policy_query", "unsupported"],
            "description": (
                "The operation requested by the user. Use 'policy_query' for "
                "questions about policies, rules, regulations, guidelines, "
                "syllabus, FAQs, or procedures rather than a specific student's "
                "ERP data."
            ),
        },
        "table": {
            "type": "string",
            "enum": ["attendance", "marks", "timetable", "policy", "unsupported"],
            "description": (
                "The ERP table relevant to the request, or 'policy' when the "
                "action is 'policy_query'."
            ),
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
                env_paths = [
                    os.path.expanduser("~/.env"),
                    os.path.join(os.path.dirname(__file__), "..", ".env"),
                ]

                for env_path in env_paths:
                    if not os.path.isfile(env_path):
                        continue

                    try:
                        with open(env_path, "r", encoding="utf-8") as file:
                            for line in file:
                                line = line.strip()

                                if line.startswith("GEMINI_API_KEY="):
                                    api_key = line.split(
                                        "=", 1
                                    )[1].strip("'\" ")
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

        clean_text = text.strip()

        # Offline deterministic mode for presentations and demos.
        # Only use it when the application explicitly has a client available.
        # Tests that construct IntentEngine(client=None) must still fail closed.
        offline_flag = os.getenv("VOXERP_OFFLINE_MODE")
        if (
            isinstance(offline_flag, str)
            and offline_flag.strip().lower() in {"1", "true", "yes"}
            and self.client is not None
        ):
            return self._offline_intent(clean_text, normalized_role, schema_map)

        prompt = self._build_prompt(
            text=clean_text,
            role=normalized_role,
            schema_map=schema_map,
        )

        if self.client is None:
            return {"action": "unsupported", "table": "unsupported", "filters": {}}

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

            intent = self._validate_intent(parsed)

            # Deterministic safety guard for explicit attendance writes.
            #
            # Gemini remains responsible for normal natural-language
            # understanding, but an unmistakable command such as
            # "Mark Vijay absent" must never randomly become unsupported.
            intent = self._apply_write_safety_guard(clean_text, intent)

            return intent

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

POLICY_QUERY:
- questions about policies, rules, regulations, guidelines, syllabus,
  FAQs, or procedures (not a specific student's ERP data)

The current user's role is: {role}

Database schema:
{schema_description}

User's spoken request:
{text}

Classification rules:

1. "attendance" queries belong to the attendance table.
2. "marks", "scores", "exam marks", or similar queries belong to the marks table.
3. Timetable or class-schedule queries belong to the timetable table.
4. A request to mark a student present or absent is a WRITE operation on attendance.
5. If the request is unrelated to VoxERP's supported operations, classify it as unsupported.
17. If the request asks about a policy, rule, regulation, guideline, syllabus, FAQ, or procedure rather than a specific student's data, classify the action as "policy_query" and the table as "policy". Do not extract student_id, student_name, subject, date, or status for policy_query requests.
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
16. Any explicit request containing an attendance write action such as "mark", "record", or "set" together with "present" or "absent" must be classified as a write operation on attendance.
""".strip()

    @staticmethod
    def _validate_intent(intent: Any) -> Dict[str, Any]:
        """Validate and normalize the model's structured result."""

        if not isinstance(intent, dict):
            return IntentEngine._fallback_intent()

        action = intent.get("action")
        table = intent.get("table")
        filters = intent.get("filters")

        if action not in {"read", "write", "policy_query", "unsupported"}:
            return IntentEngine._fallback_intent()

        if table not in {
            "attendance",
            "marks",
            "timetable",
            "policy",
            "unsupported",
        }:
            return IntentEngine._fallback_intent()

        if action == "policy_query" and table != "policy":
            return IntentEngine._fallback_intent()
        if action != "policy_query" and table == "policy":
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

        # Sanitize student_name and subject to avoid question words or
        # self-references becoming student targets (e.g. "what", "what's",
        # "my", "me"). This ensures the intent contract stays safe and
        # RBAC receives None for ambiguous/self references.
        cleaned_filters["student_name"] = IntentEngine._sanitize_student_name(cleaned_filters.get("student_name"))
        cleaned_filters["subject"] = IntentEngine._sanitize_subject(cleaned_filters.get("subject"))

        return {
            "action": action,
            "table": table,
            "filters": cleaned_filters,
        }

    @staticmethod
    def _sanitize_student_name(name: Any) -> Any:
        """Normalize student_name values: return None for pronouns, question
        words, or other non-name tokens. Preserve real-looking names.
        """
        if not isinstance(name, str):
            return None

        candidate = name.strip()
        if not candidate:
            return None

        # Strip possessive trailing "'s" or trailing punctuation
        candidate = re.sub(r"(?:'s)$", "", candidate)
        candidate = candidate.strip("\"' .?,!")

        lower = candidate.lower()
        forbidden = {
            "me",
            "my",
            "myself",
            "i",
            "you",
            "your",
            "what",
            "whats",
            "what's",
            "which",
            "who",
            "whos",
            "who's",
            "how",
            "show",
            "tell",
            "give",
            "the",
            "that",
            "this",
            "these",
            "those",
            "attendance",
        }

        if lower in forbidden:
            return None

        # If the token contains whitespace or looks like a sentence fragment,
        # avoid treating it as a name.
        if " " in candidate or any(c in candidate for c in "?/;:"):
            return None

        return candidate

    @staticmethod
    def _sanitize_subject(subject: Any) -> Any:
        if not isinstance(subject, str):
            return None
        candidate = subject.strip()
        if not candidate:
            return None
        # simple sanitation: avoid question words being a subject
        if candidate.lower() in {"what", "whats", "what's", "which", "that", "this"}:
            return None
        return candidate

    @staticmethod
    def _apply_write_safety_guard(
        text: str,
        intent: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Deterministically recognize unmistakable attendance-write commands.

        Gemini remains the primary intent engine. This guard only overrides
        the model when the user's wording itself clearly indicates an
        attendance write.
        """

        normalized = text.lower().strip()

        write_verbs = (
            "mark",
            "record",
            "set",
            "update",
        )

        attendance_statuses = {
            "absent": "absent",
            "present": "present",
        }

        has_write_verb = any(
            re.search(rf"\b{re.escape(verb)}\b", normalized)
            for verb in write_verbs
        )

        detected_status = None

        for word, status in attendance_statuses.items():
            if re.search(rf"\b{word}\b", normalized):
                detected_status = status
                break

        if not has_write_verb or detected_status is None:
            return intent

        # Only attendance writes are covered by this deterministic guard.
        guarded_filters = dict(intent.get("filters", {}))

        guarded_filters["status"] = detected_status

        # If Gemini failed to extract the student name, recover an explicitly
        # mentioned name from common commands such as:
        #   Mark Vijay absent
        #   Record Vijay present
        #   Mark Vijay absent in DBMS
        if not guarded_filters.get("student_name"):
            name_match = re.search(
                r"\b(?:mark|record|set|update)"
                r"(?:\s+attendance)?"
                r"\s+"
                r"([A-Za-z][A-Za-z0-9_-]*)"
                r"\s+(?:as\s+)?(?:present|absent)\b",
                text,
                flags=re.IGNORECASE,
            )

            if name_match:
                candidate = name_match.group(1)
                # Sanitize extracted candidate before treating it as a name
                sanitized = IntentEngine._sanitize_student_name(candidate)
                if sanitized:
                    guarded_filters["student_name"] = sanitized

        # Recover a subject only when it is explicitly introduced by "in".
        # Example:
        #   Mark Vijay absent in DBMS
        #
        # We deliberately do not guess subjects from arbitrary words.
        if not guarded_filters.get("subject"):
            subject_match = re.search(
                r"\bin\s+([A-Za-z][A-Za-z0-9&._-]*)\b",
                text,
                flags=re.IGNORECASE,
            )

            if subject_match:
                candidate_subject = subject_match.group(1)
                sanitized_subject = IntentEngine._sanitize_subject(candidate_subject)
                if sanitized_subject:
                    guarded_filters["subject"] = sanitized_subject

        return {
            "action": "write",
            "table": "attendance",
            "filters": {
                "student_id": guarded_filters.get("student_id"),
                "student_name": guarded_filters.get("student_name"),
                "subject": guarded_filters.get("subject"),
                "date": guarded_filters.get("date"),
                "status": detected_status,
            },
        }

    @staticmethod
    def _offline_intent(text: str, role: str, schema_map: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic, presentation-friendly intent parser used when
        VOXERP_OFFLINE_MODE is enabled. Produces the same intent contract
        as the Gemini path but using simple heuristics.
        """

        lowered = (text or "").strip()
        lowered_l = lowered.lower()

        # Short-circuit obvious unsupported requests.
        if any(token in lowered_l for token in ("weather", "asdfghjkl")):
            return IntentEngine._fallback_intent()

        # Detect explicit write commands first using the safety guard.
        write_verbs = ("mark", "record", "set", "update")
        if any(re.search(rf"\b{re.escape(v)}\b", lowered_l) for v in write_verbs) and any(
            w in lowered_l for w in ("absent", "present")
        ):
            # Use existing deterministic guard to extract name/subject/status.
            return IntentEngine._apply_write_safety_guard(text, {"action": "write", "table": "attendance", "filters": {}})

        # Timetable
        if "timetable" in lowered_l or "schedule" in lowered_l or "class schedule" in lowered_l:
            student_name = IntentEngine._offline_extract_student_name(text)

            return IntentEngine._validate_intent({
                "action": "read",
                "table": "timetable",
                "filters": {
                    "student_id": None,
                    "student_name": student_name,
                    "subject": None,
                    "date": None,
                    "status": None,
                },
            })

        # Marks detection
        if "marks" in lowered_l or ("mark" in lowered_l and "absent" not in lowered_l):
            # Try to extract subject
            subject = None
            m = re.search(r"\bin\s+([A-Za-z][A-Za-z0-9&._\- ]*)\b", text)
            if m:
                subject = m.group(1).strip()
            else:
                for candidate in ("DBMS", "AI", "Maths", "Operating Systems", "Computer Networks"):
                    if candidate.lower() in lowered_l:
                        subject = candidate
                        break

            # Try to extract an explicit student name.
            # Examples:
            #   Show me Vijay marks
            #   Show me Vijay's marks
            #   Vijay marks
            student_name = IntentEngine._offline_extract_student_name(text)

            if student_name is None:
                m2 = re.search(
                    r"\bshow\s+me\s+([A-Za-z][A-Za-z0-9_-]*)"
                    r"(?:'s)?\s+(?:marks|scores?)\b",
                    text,
                    flags=re.IGNORECASE,
                )
                if m2:
                    student_name = IntentEngine._sanitize_student_name(m2.group(1))

            if student_name is None:
                m3 = re.search(
                    r"\b([A-Za-z][A-Za-z0-9_-]*)(?:'s)?\s+(?:marks|scores?)\b",
                    text,
                    flags=re.IGNORECASE,
                )
                if m3:
                    candidate = m3.group(1)
                    if candidate.lower() not in {"show", "me", "my", "the"}:
                        student_name = IntentEngine._sanitize_student_name(candidate)

            return IntentEngine._validate_intent({
                "action": "read",
                "table": "marks",
                "filters": {
                    "student_id": None,
                    "student_name": student_name,
                    "subject": subject,
                    "date": None,
                    "status": None,
                },
            })

        # Attendance detection
        if "attendance" in lowered_l or "how much attendance" in lowered_l:
            subject = None
            m = re.search(r"\b(dbms|ai|maths|operating systems|computer networks)\b", lowered_l)
            if m:
                subject = m.group(1)
                # Beautify common subjects
                if subject.lower() == "dbms":
                    subject = "DBMS"
                elif subject.lower() == "ai":
                    subject = "AI"
                elif subject.lower() == "maths":
                    subject = "Maths"
                elif subject.lower() == "operating systems":
                    subject = "Operating Systems"
                elif subject.lower() == "computer networks":
                    subject = "Computer Networks"
            else:
                m2 = re.search(r"\b(in|for)\s+([A-Za-z][A-Za-z0-9&._\- ]*)\b", text)
                if m2:
                    subject = m2.group(2).strip()

            # student_name extraction similar to marks
            student_name = IntentEngine._offline_extract_student_name(text)

            return IntentEngine._validate_intent({
                "action": "read",
                "table": "attendance",
                "filters": {
                    "student_id": None,
                    "student_name": student_name,
                    "subject": subject,
                    "date": None,
                    "status": None,
                },
            })

        # Default to unsupported
        return IntentEngine._fallback_intent()

    @staticmethod
    def _offline_extract_student_name(text: str) -> Any:
        """Extract an explicitly named student from common offline queries."""

        if not isinstance(text, str):
            return None

        # Supported forms:
        #   Vijay's marks
        #   Show me Vijay marks
        #   Show me Vijay attendance for DBMS
        #   Show me Vijay timetable
        #   Vijay timetable

        patterns = [
            r"\b([A-Z][a-z]+)'s\s+(?:marks?|scores?|attendance|timetable|schedule)\b",
            r"\bshow\s+me\s+([A-Za-z][A-Za-z0-9_-]*)(?:'s)?\s+(?:marks?|scores?|attendance|timetable|schedule)\b",
            r"\bshow\s+([A-Za-z][A-Za-z0-9_-]*)(?:'s)?\s+(?:marks?|scores?|attendance|timetable|schedule)\b",
            r"^\s*([A-Za-z][A-Za-z0-9_-]*)(?:'s)?\s+(?:marks?|scores?|attendance|timetable|schedule)\b",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue

            candidate = IntentEngine._sanitize_student_name(match.group(1))
            if candidate:
                return candidate

        return None

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

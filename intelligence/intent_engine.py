from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

from google import genai


MODEL_NAME = "gemini-3.6-flash"

# Local Gemma 4 E4B model.
# This is the primary local intent-classification engine.
GEMMA_MODEL_NAME = os.getenv(
    "VOXERP_GEMMA_MODEL",
    "mlx-community/gemma-4-e4b-it-4bit",
)
GEMMA_MAX_TOKENS = int(os.getenv("VOXERP_GEMMA_MAX_TOKENS", "80"))
GEMMA_TEMPERATURE = float(os.getenv("VOXERP_GEMMA_TEMPERATURE", "0.0"))
GEMMA_REPETITION_PENALTY = float(
    os.getenv("VOXERP_GEMMA_REPETITION_PENALTY", "1.05")
)


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
                "period": {
                    "type": ["integer", "null"],
                    "description": "Attendance period number if explicitly mentioned, from 1 to 10.",
                },
            },
            "required": [
                "student_id",
                "student_name",
                "subject",
                "date",
                "status",
                "period",
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
        """
        Initialize the VoxERP intent engine.

        Local Gemma 4 E4B is the normal inference engine.
        An explicitly injected Gemini client is retained only for
        compatibility with existing tests.
        """
        self.client = client
        self.model = None
        self.processor = None
        self.gemma_available = False

        # Explicitly injected Gemini clients are preserved for tests.
        if self.client is not None:
            return

        try:
            from mlx_vlm import load

            self.model, self.processor = load(GEMMA_MODEL_NAME)
            self.gemma_available = True
        except Exception:
            # Fail closed. Never silently fall back to a cloud API.
            self.model = None
            self.processor = None
            self.gemma_available = False

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

        # Deterministic handling for unmistakable attendance-write commands.
        # These commands are explicit enough that Gemini classification is
        # unnecessary and could introduce avoidable wording-dependent failures.
        write_verbs = ("mark", "record", "set", "update")
        has_write_verb = any(
            re.search(rf"\b{re.escape(verb)}\b", clean_text, flags=re.IGNORECASE)
            for verb in write_verbs
        )
        has_attendance_status = any(
            re.search(rf"\b{status}\b", clean_text, flags=re.IGNORECASE)
            for status in ("absent", "present")
        )

        if has_write_verb and has_attendance_status:
            return self._apply_write_safety_guard(
                clean_text,
                {"action": "write", "table": "attendance", "filters": {}},
            )

        # Offline deterministic mode for presentations and demos.
        # Only use it when the application explicitly has a client available.
        # Tests that construct IntentEngine(client=None) must still fail closed.
        offline_flag = os.getenv("VOXERP_OFFLINE_MODE")
        if (
            isinstance(offline_flag, str)
            and offline_flag.strip().lower() in {"1", "true", "yes"}
            and (self.gemma_available or self.client is not None)
        ):
            return self._offline_intent(clean_text, normalized_role, schema_map)

        # ========================================================
        # Local Gemma 4 E4B — primary intent classifier
        # ========================================================

        if self.gemma_available:
            try:
                parsed = self._generate_gemma_intent(
                    text=clean_text,
                    role=normalized_role,
                    schema_map=schema_map,
                )

                intent = self._validate_intent(parsed)

                # Recover explicit targets that Gemma may omit.
                intent = self._apply_explicit_student_target(clean_text, intent)

                # Existing deterministic safety layer remains active.
                return self._apply_write_safety_guard(clean_text, intent)

            except Exception:
                return self._fallback_intent()

        # ========================================================
        # Compatibility path for explicitly injected Gemini clients
        # ========================================================

        if self.client is not None:
            try:
                prompt = self._build_prompt(
                    text=clean_text,
                    role=normalized_role,
                    schema_map=schema_map,
                )

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

                return self._apply_write_safety_guard(clean_text, intent)

            except Exception:
                return self._fallback_intent()

        return self._fallback_intent()


    def _apply_explicit_student_target(
        self,
        text: str,
        intent: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Recover an explicit student target when the intent classifier
        omitted it.

        This only exposes the target to the existing RBAC layer.
        It does not authorize the target.
        """
        if not isinstance(text, str) or not isinstance(intent, dict):
            return intent

        filters = intent.get("filters")
        if not isinstance(filters, dict):
            return intent

        # Never overwrite a target already extracted by the model.
        if filters.get("student_id") or filters.get("student_name"):
            return intent

        match = re.search(
            r"\bstudent\s+([A-Za-z0-9_-]+)(?:['’]s)?(?=\s+(?:marks?|attendance|timetable|results?|policy)\b|[\s?.!,]*$)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            filters["student_id"] = str(match.group(1))

        return intent

    def _generate_gemma_intent(
        self,
        text: str,
        role: str,
        schema_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate a VoxERP intent using local Gemma 4 E4B."""

        if self.model is None or self.processor is None:
            raise RuntimeError("Local Gemma model is not available")

        tokenizer = getattr(self.processor, "tokenizer", None)

        if tokenizer is None:
            tokenizer = self.processor

        system_prompt = f"""
You are the VoxERP intent classification engine.

Return ONLY one valid JSON object.
Do not answer the user's question.
Do not use Markdown.
Do not add explanations.
Do not invent database tables, students, subjects, dates, or filters.
Do not make authorization decisions. RBAC handles authorization separately.

The user's role is: {role}

Use exactly this JSON structure:

{{
  "action": "read|write|policy_query|unsupported",
  "table": "attendance|marks|timetable|policy|unsupported",
  "filters": {{
    "student_id": null,
    "student_name": null,
    "subject": null,
    "date": null,
    "status": null,
    "period": null
  }}
}}

Rules:
- Attendance queries -> read / attendance.
- Marks, scores, exam marks, exam results -> read / marks.
- Timetable or class schedule -> read / timetable.
- Mark, record, set, or update attendance as present or absent
  -> write / attendance.
- Policy, rules, regulations, guidelines, syllabus, FAQ, or procedures
  -> policy_query / policy.
- Unsupported requests -> unsupported / unsupported.
- Extract student_id only when explicitly provided.
- Extract student_name only when explicitly mentioned.
- "my", "me", or "myself" means self-reference.
- Extract subject exactly as spoken.
- Extract date only when explicitly mentioned.
- For attendance writes, extract status only when explicitly stated.
- Extract period only when explicitly stated.
- Period must be an integer from 1 to 10.
- Never guess missing information.
- Never decide authorization.
- Never invent filters.

Database schema context:
{json.dumps(schema_map, ensure_ascii=False, separators=(",", ":"))}
""".strip()

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": text,
            },
        ]

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

        from mlx_vlm import generate

        result = generate(
            self.model,
            self.processor,
            prompt=prompt,
            max_tokens=GEMMA_MAX_TOKENS,
            temperature=GEMMA_TEMPERATURE,
            repetition_penalty=GEMMA_REPETITION_PENALTY,
            repetition_context_size=32,
            top_p=1.0,
            top_k=1,
        )

        raw_text = getattr(result, "text", None)

        if not raw_text:
            raw_text = str(result)

        return self._extract_json_object(raw_text)

    @staticmethod
    def _extract_json_object(raw_text: str) -> Dict[str, Any]:
        """Safely extract a JSON object from Gemma output."""

        if not isinstance(raw_text, str):
            raise ValueError("Model output is not text")

        candidate = raw_text.strip()

        # Remove Markdown fences if Gemma adds them.
        candidate = re.sub(
            r"^```(?:json)?\s*",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(r"\s*```$", "", candidate)

        try:
            parsed = json.loads(candidate)

            if isinstance(parsed, dict):
                return parsed

        except json.JSONDecodeError:
            pass

        # Recover JSON if surrounding text was generated.
        start = candidate.find("{")

        if start == -1:
            raise ValueError("No JSON object found in model output")

        decoder = json.JSONDecoder()
        parsed, _ = decoder.raw_decode(candidate[start:])

        if not isinstance(parsed, dict):
            raise ValueError("Model output is not a JSON object")

        return parsed

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
10a. For attendance writes, extract the period only when the user explicitly mentions it, such as "period 6", "6th period", or "6th hour". The period must be an integer from 1 to 10. Never guess a missing period.
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
            "period",
        }

        cleaned_filters = {
            key: filters.get(key)
            for key in allowed_filters
        }

        # Keep student IDs canonical across model outputs. Gemma may emit
        # numeric IDs as integers (for example, 2) while RBAC expects
        # string IDs (for example, "2").
        raw_student_id = cleaned_filters.get("student_id")
        if isinstance(raw_student_id, int) and not isinstance(raw_student_id, bool):
            cleaned_filters["student_id"] = str(raw_student_id)

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

        # Explicitly preserve a non-self student target.
        # Examples:
        #   Mark student 2 absent ...
        #   Mark student-2 absent ...
        #
        # Do not reinterpret this as self-reference. RBAC will fail closed
        # when the requesting student is not authorized for that target.
        if not guarded_filters.get("student_id") and not guarded_filters.get("student_name"):
            explicit_student_match = re.search(
                r"\b(?:student|student_id|student-id)\s*[-:]?\s*(\d+)\b",
                text,
                flags=re.IGNORECASE,
            )

            if explicit_student_match:
                guarded_filters["student_id"] = explicit_student_match.group(1)

        # Recover an explicitly mentioned student name from commands such as:
        #   Mark Vijay absent
        #   Record Vijay present
        if (
            not guarded_filters.get("student_name")
            and not guarded_filters.get("student_id")
        ):
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

                # Do not treat self-reference or generic target words as names.
                if candidate.lower() not in {
                    "my",
                    "me",
                    "myself",
                    "student",
                }:
                    sanitized = IntentEngine._sanitize_student_name(candidate)
                    if sanitized:
                        guarded_filters["student_name"] = sanitized

        # Recover multi-word subjects only when explicitly bounded.
        #
        # Examples:
        #   Mark Vijay absent in Distributed Computing
        #   Mark my Distributed Computing attendance absent
        #   Mark me absent for Distributed Computing period 6
        #
        # We do not guess arbitrary words as a subject.
        if not guarded_filters.get("subject"):
            subject_match = re.search(
                r"\bin\s+(.+?)(?=\s+for\s+(?:period|hour)\b|\s+(?:present|absent)\b|$)",
                text,
                flags=re.IGNORECASE,
            )

            if subject_match:
                candidate_subject = subject_match.group(1).strip()
                sanitized_subject = IntentEngine._sanitize_subject(candidate_subject)

                if sanitized_subject:
                    guarded_filters["subject"] = sanitized_subject

        # Also support commands where "for" introduces the subject:
        #   Mark me absent for Distributed Computing period 6
        #   Mark me present for DBMS hour 2
        #
        # The period/hour boundary prevents us from treating the rest of the
        # sentence as a subject.
        if not guarded_filters.get("subject"):
            subject_match = re.search(
                r"\bfor\s+(.+?)(?=\s+(?:period|hour)\s*(?:number\s*)?\d{1,2}\b|$)",
                text,
                flags=re.IGNORECASE,
            )

            if subject_match:
                candidate_subject = subject_match.group(1).strip()
                sanitized_subject = IntentEngine._sanitize_subject(candidate_subject)

                if sanitized_subject:
                    guarded_filters["subject"] = sanitized_subject

        # Support natural self-reference commands such as:
        #   Mark my Distributed Computing attendance absent
        #   Mark me DBMS attendance present
        #
        # "attendance" provides an explicit boundary, so we do not guess
        # arbitrary words as the subject.
        if not guarded_filters.get("subject"):
            self_subject_match = re.search(
                r"\b(?:mark|record|set|update)"
                r"\s+(?:my|me|myself)\s+"
                r"(.+?)\s+attendance\b",
                text,
                flags=re.IGNORECASE,
            )

            if self_subject_match:
                candidate_subject = self_subject_match.group(1).strip()
                sanitized_subject = IntentEngine._sanitize_subject(candidate_subject)

                if sanitized_subject:
                    guarded_filters["subject"] = sanitized_subject

        # Also support the compact form:
        #   Mark my DBMS absent
        #   Mark me DBMS present
        if not guarded_filters.get("subject"):
            self_subject_match = re.search(
                r"\b(?:mark|record|set|update)"
                r"\s+(?:my|me|myself)\s+"
                r"([A-Za-z][A-Za-z0-9&._-]*)\s+"
                r"(?:present|absent)\b",
                text,
                flags=re.IGNORECASE,
            )

            if self_subject_match:
                candidate_subject = self_subject_match.group(1)
                sanitized_subject = IntentEngine._sanitize_subject(candidate_subject)

                if sanitized_subject:
                    guarded_filters["subject"] = sanitized_subject

        # Extract an attendance period only when it is explicitly stated.
        # Examples: "period 6", "hour 6", "6th period", "6th hour".
        period = guarded_filters.get("period")

        if period is None:
            period_match = re.search(
                r"\b(?:period|hour)\s*(?:number\s*)?(\d{1,2})\b"
                r"|\b(\d{1,2})(?:st|nd|rd|th)\s+(?:period|hour)\b",
                text,
                flags=re.IGNORECASE,
            )

            if period_match:
                detected_period = next(
                    (
                        group
                        for group in period_match.groups()
                        if group is not None
                    ),
                    None,
                )

                if detected_period is not None:
                    period_value = int(detected_period)
                    if 1 <= period_value <= 10:
                        period = period_value

        return {
            "action": "write",
            "table": "attendance",
            "filters": {
                "student_id": guarded_filters.get("student_id"),
                "student_name": guarded_filters.get("student_name"),
                "subject": guarded_filters.get("subject"),
                "date": guarded_filters.get("date"),
                "status": detected_status,
                "period": period,
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

        # Policy questions must be routed to RAG before generic
        # attendance/marks/timetable keyword detection.
        policy_terms = (
            "policy",
            "policies",
            "rule",
            "rules",
            "regulation",
            "regulations",
            "guideline",
            "guidelines",
            "syllabus",
            "faq",
            "procedure",
            "procedures",
        )
        if any(term in lowered_l for term in policy_terms):
            return IntentEngine._validate_intent({
                "action": "policy_query",
                "table": "policy",
                "filters": {
                    "student_id": None,
                    "student_name": None,
                    "subject": None,
                    "date": None,
                    "status": None,
                },
            })

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
        # Support natural variations such as marks, scores, exam marks,
        # and score-based questions without hardcoding specific queries.
        marks_terms = (
            "marks",
            "mark",
            "scores",
            "score",
            "exam result",
            "exam results",
            "results",
        )

        is_marks_query = any(
            term in lowered_l for term in marks_terms
        )

        # Avoid treating attendance write commands such as
        # "mark me absent" as marks queries.
        if is_marks_query and not (
            ("absent" in lowered_l or "present" in lowered_l)
            and any(
                action_word in lowered_l
                for action_word in ("mark", "record", "set")
            )
        ):
            # Try to extract an explicitly mentioned subject/course.
            # Supports course codes and natural-language course titles without
            # maintaining a hardcoded course list.

            subject = None

            # Course-code style tokens, e.g. AD3491, CS3551, MA3391.
            # Require both letters and digits so ordinary words are not
            # accidentally treated as course codes.
            course_code_match = re.search(
                r"\b(?=[A-Za-z0-9]*[A-Za-z])(?=[A-Za-z0-9]*\d)"
                r"[A-Za-z][A-Za-z0-9._-]*\b",
                text,
            )

            if course_code_match:
                subject = course_code_match.group(0).strip()
            else:
                # Natural-language subject after "in" or "for".
                subject_match = re.search(
                    r"\b(?:in|for)\s+(.+?)(?=\s+(?:marks?|scores?|results?)\b|[?.!,]*$)",
                    text,
                    flags=re.IGNORECASE,
                )

                if subject_match:
                    candidate = subject_match.group(1).strip(" \t\n?.!,")
                    if candidate:
                        subject = candidate

                # Subject before "marks/scores/results", e.g.
                # "Show my Distributed Computing marks".
                if subject is None:
                    before_marks = re.search(
                        r"\b(?:my\s+)?(.+?)\s+(?:marks?|scores?|results?)\b",
                        text,
                        flags=re.IGNORECASE,
                    )

                    if before_marks:
                        candidate = before_marks.group(1).strip()

                        # Remove conversational prefixes that are not part
                        # of the subject.
                        candidate = re.sub(
                            r"^(?:what\s+are|what\s+is|show|give|tell\s+me|"
                            r"get|display)\s+(?:my\s+)?",
                            "",
                            candidate,
                            flags=re.IGNORECASE,
                        ).strip()

                        if candidate and candidate.lower() not in {
                            "my",
                            "me",
                            "the",
                            "exam",
                            "exam result",
                            "exam results",
                            "result",
                            "results",
                            "score",
                            "scores",
                            "mark",
                            "marks",
                        }:
                            subject = candidate

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

            # Explicit subject before "attendance":
            #   What is my DBMS attendance?
            #   Show my Distributed Computing attendance.
            subject_before_attendance = re.search(
                r"\b(?:my\s+)?(.+?)\s+attendance\b",
                text,
                flags=re.IGNORECASE,
            )

            if subject_before_attendance:
                candidate = subject_before_attendance.group(1).strip()

                # Remove common conversational prefixes.
                candidate = re.sub(
                    r"^(?:what\s+is|what\s+are|show|give|tell\s+me|"
                    r"get|display)\s+(?:my\s+)?",
                    "",
                    candidate,
                    flags=re.IGNORECASE,
                ).strip()

                if candidate and candidate.lower() not in {
                    "my",
                    "me",
                    "the",
                    "your",
                    "student",
                }:
                    subject = candidate

            # Explicit subject after "in" or "for":
            #   What is my attendance for DBMS?
            #   Show attendance in Distributed Computing.
            if subject is None:
                subject_match = re.search(
                    r"\b(?:in|for)\s+(.+?)(?=\s+attendance\b|[?.!,]*$)",
                    text,
                    flags=re.IGNORECASE,
                )

                if subject_match:
                    candidate = subject_match.group(1).strip(" \t\n?.!,")
                    if candidate:
                        subject = candidate

            # Student name extraction.
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
                    "period": None,
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
                "period": None,
            },
        }

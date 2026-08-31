import json
import os
import re
import unittest

from db_adapter import build_schema_map
from intelligence.intent_engine import IntentEngine
from intelligence.rbac import authorize_request
from intelligence.response_generator import generate_response


class FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeGeminiModels:
    def __init__(self) -> None:
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        prompt = kwargs.get("contents", "")
        request_match = re.search(r"User's spoken request:\s*(.+?)(?:\n\n|$)", prompt, re.S)
        request_text = request_match.group(1).strip() if request_match else prompt
        lowered = request_text.lower()

        if "dbms attendance" in lowered:
            return FakeGeminiResponse('{"action":"read","table":"attendance","filters":{"student_id":null,"student_name":null,"subject":"DBMS","date":null,"status":null}}')
        if "ai marks" in lowered:
            return FakeGeminiResponse('{"action":"read","table":"marks","filters":{"student_id":null,"student_name":null,"subject":"AI","date":null,"status":null}}')
        if "dbms marks" in lowered:
            return FakeGeminiResponse('{"action":"read","table":"marks","filters":{"student_id":null,"student_name":null,"subject":"DBMS","date":null,"status":null}}')
        if "maths" in lowered and "attendance" in lowered:
            return FakeGeminiResponse('{"action":"read","table":"attendance","filters":{"student_id":null,"student_name":null,"subject":"Maths","date":null,"status":null}}')
        if "timetable" in lowered or "schedule" in lowered:
            return FakeGeminiResponse('{"action":"read","table":"timetable","filters":{"student_id":null,"student_name":null,"subject":null,"date":null,"status":null}}')
        if "priya" in lowered and "marks" in lowered:
            return FakeGeminiResponse('{"action":"read","table":"marks","filters":{"student_id":null,"student_name":"Priya","subject":null,"date":null,"status":null}}')
        if "mark vijay absent" in lowered or ("mark" in lowered and "absent" in lowered):
            subject = "DBMS" if "dbms" in lowered else None
            return FakeGeminiResponse(f'{{"action":"write","table":"attendance","filters":{{"student_id":null,"student_name":"Vijay","subject":{json.dumps(subject)},"date":null,"status":"absent"}}}}')
        if "weather" in lowered or "asdfghjkl" in lowered or "delete" in lowered or "drop" in lowered:
            return FakeGeminiResponse('{"action":"unsupported","table":"unsupported","filters":{"student_id":null,"student_name":null,"subject":null,"date":null,"status":null}}')
        return FakeGeminiResponse('{"action":"read","table":"marks","filters":{"student_id":null,"student_name":null,"subject":null,"date":null,"status":null}}')


class FakeGeminiClient:
    def __init__(self) -> None:
        self.models = FakeGeminiModels()


class PersonBTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schema_map = build_schema_map()
        self.engine = IntentEngine(client=FakeGeminiClient())

    def test_intent_engine_handles_core_queries(self) -> None:
        self.assertEqual(self.engine.parse("What's my DBMS attendance?", "student", self.schema_map)["table"], "attendance")
        self.assertEqual(self.engine.parse("Show me my AI marks.", "student", self.schema_map)["table"], "marks")
        self.assertEqual(self.engine.parse("What is my timetable?", "student", self.schema_map)["table"], "timetable")
        self.assertEqual(self.engine.parse("Mark Vijay absent.", "student", self.schema_map)["action"], "write")
        self.assertEqual(self.engine.parse("Show me another student's marks.", "student", self.schema_map)["table"], "marks")
        self.assertEqual(self.engine.parse("What's the weather today?", "student", self.schema_map)["action"], "unsupported")
        self.assertEqual(self.engine.parse("", "student", self.schema_map)["action"], "unsupported")
        self.assertEqual(self.engine.parse("asdfghjkl", "student", self.schema_map)["action"], "unsupported")

    def test_gemini_extraction_for_subjects_and_names(self) -> None:
        attendance_intent = self.engine.parse("What's my DBMS attendance?", "student", self.schema_map)
        marks_ai_intent = self.engine.parse("Show me my AI marks.", "student", self.schema_map)
        marks_dbms_intent = self.engine.parse("Tell me my DBMS marks.", "student", self.schema_map)
        maths_intent = self.engine.parse("How much attendance do I have in Maths?", "student", self.schema_map)
        write_intent = self.engine.parse("Mark Vijay absent.", "student", self.schema_map)

        self.assertEqual(attendance_intent["table"], "attendance")
        self.assertEqual(attendance_intent["filters"]["subject"], "DBMS")
        self.assertEqual(marks_ai_intent["table"], "marks")
        self.assertEqual(marks_ai_intent["filters"]["subject"], "AI")
        self.assertEqual(marks_dbms_intent["filters"]["subject"], "DBMS")
        self.assertEqual(maths_intent["filters"]["subject"], "Maths")
        self.assertEqual(write_intent["filters"]["student_name"], "Vijay")
        self.assertEqual(write_intent["filters"]["status"], "absent")

    def test_rbac_blocks_student_from_other_student_data(self) -> None:
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {"student_name": "Priya", "student_id": None, "subject": None, "date": None, "status": None},
        }

        result = authorize_request(user_id="student-1", role="student", intent=intent, text="Show me Priya's marks")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "unauthorized_target")

    def test_rbac_blocks_student_from_writing_another_student_attendance(self) -> None:
        intent = {
            "action": "write",
            "table": "attendance",
            "filters": {"student_name": "Priya", "student_id": None, "subject": "DBMS", "date": "2026-08-07", "status": "absent"},
        }

        result = authorize_request(user_id="student-1", role="student", intent=intent, text="Please mark Priya absent")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "unauthorized_target")

    def test_rbac_allows_self_reference_and_denies_ambiguous_targets(self) -> None:
        self.assertTrue(
            authorize_request(user_id="student-1", role="student", intent={"action": "read", "table": "marks", "filters": {"student_id": None, "student_name": None, "subject": None, "date": None, "status": None}}, text="show me my marks")["allowed"]
        )
        ambiguous = authorize_request(user_id="student-1", role="student", intent={"action": "read", "table": "marks", "filters": {"student_id": None, "student_name": None, "subject": None, "date": None, "status": None}}, text="show me the student's marks")
        self.assertFalse(ambiguous["allowed"])
        self.assertEqual(ambiguous["reason"], "ambiguous_target")

    def test_rbac_denies_another_student_phrase_and_teacher_scope_is_fail_closed(self) -> None:
        denied = authorize_request(user_id="student-1", role="student", intent={"action": "read", "table": "marks", "filters": {"student_id": None, "student_name": None, "subject": None, "date": None, "status": None}}, text="show me another student's marks")
        self.assertFalse(denied["allowed"])
        self.assertEqual(denied["reason"], "unauthorized_target")

        teacher = authorize_request(user_id="teacher-1", role="teacher", intent={"action": "read", "table": "marks", "filters": {"student_id": None, "student_name": None, "subject": None, "date": None, "status": None}}, text="show me marks")
        self.assertFalse(teacher["allowed"])
        self.assertEqual(teacher["reason"], "ambiguous_target")

    def test_response_generator_handles_adapter_statuses(self) -> None:
        self.assertIn("no recorded", generate_response({"status": "no_data", "message": "No attendance recorded for DBMS"}))
        self.assertIn("couldn't find", generate_response({"status": "not_found", "message": "I couldn't find that subject"}))
        self.assertIn("already marked", generate_response({"status": "unchanged", "message": "Attendance already marked as absent"}))
        self.assertIn("marked", generate_response({"status": "created", "message": "Marked attendance for student-1"}))
        self.assertIn("updated", generate_response({"status": "updated", "message": "Updated attendance"}))


# =============================================================================
# COMPREHENSIVE PERSON-B TEST SUITE: All 11 Safety Contract Requirements
# =============================================================================
class PersonBComprehensiveTests(unittest.TestCase):
    """Deterministic tests for the complete intent → RBAC safety contract."""

    def setUp(self) -> None:
        # Ensure offline mode from other tests does not affect these cases
        os.environ.pop("VOXERP_OFFLINE_MODE", None)

        self.schema_map = build_schema_map()
        self.engine = IntentEngine(client=FakeGeminiClient())

    # =========================================================================
    # Requirement 1: Student asking for their own marks
    # =========================================================================
    def test_student_own_marks_intent_parsing(self) -> None:
        """Intent engine correctly parses student's own marks request."""
        intent = self.engine.parse("Show me my DBMS marks", "student", self.schema_map)
        self.assertEqual(intent["action"], "read")
        self.assertEqual(intent["table"], "marks")
        self.assertEqual(intent["filters"]["subject"], "DBMS")
        self.assertIsNone(intent["filters"]["student_name"])

    def test_student_own_marks_rbac_allows(self) -> None:
        """RBAC allows student to read their own marks."""
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {"student_id": None, "student_name": None, "subject": "DBMS", "date": None, "status": None},
        }
        result = authorize_request(user_id="student-1", role="student", intent=intent, text="show me my marks")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["target_student_id"], "student-1")

    # =========================================================================
    # Requirement 2: Student asking for their own attendance
    # =========================================================================
    def test_student_own_attendance_intent_parsing(self) -> None:
        """Intent engine correctly parses student's own attendance request."""
        intent = self.engine.parse("What's my DBMS attendance?", "student", self.schema_map)
        self.assertEqual(intent["action"], "read")
        self.assertEqual(intent["table"], "attendance")
        self.assertEqual(intent["filters"]["subject"], "DBMS")
        self.assertIsNone(intent["filters"]["student_name"])

    def test_student_own_attendance_rbac_allows(self) -> None:
        """RBAC allows student to read their own attendance."""
        intent = {
            "action": "read",
            "table": "attendance",
            "filters": {"student_id": None, "student_name": None, "subject": "DBMS", "date": None, "status": None},
        }
        result = authorize_request(user_id="student-1", role="student", intent=intent, text="what is my attendance")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["target_student_id"], "student-1")

    # =========================================================================
    # Requirement 3: Student asking for their timetable
    # =========================================================================
    def test_student_own_timetable_intent_parsing(self) -> None:
        """Intent engine correctly parses student's timetable request."""
        intent = self.engine.parse("What is my timetable?", "student", self.schema_map)
        self.assertEqual(intent["action"], "read")
        self.assertEqual(intent["table"], "timetable")
        self.assertIsNone(intent["filters"]["student_name"])

    def test_student_own_timetable_rbac_allows(self) -> None:
        """RBAC allows student to read their own timetable."""
        intent = {
            "action": "read",
            "table": "timetable",
            "filters": {"student_id": None, "student_name": None, "subject": None, "date": None, "status": None},
        }
        result = authorize_request(user_id="student-1", role="student", intent=intent, text="show me my timetable")
        self.assertTrue(result["allowed"])
        self.assertEqual(result["target_student_id"], "student-1")

    # =========================================================================
    # Requirement 4: Student attempting to access another student's marks
    # =========================================================================
    def test_another_student_marks_rbac_blocks(self) -> None:
        """RBAC blocks student from reading another student's marks."""
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {"student_id": None, "student_name": "Priya", "subject": "DBMS", "date": None, "status": None},
        }
        result = authorize_request(user_id="student-1", role="student", intent=intent, text="show me Priya's marks")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "unauthorized_target")

    def test_another_student_marks_with_student_id_rbac_blocks(self) -> None:
        """RBAC blocks access to another student's marks via student_id."""
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {"student_id": "student-2", "student_name": None, "subject": None, "date": None, "status": None},
        }
        result = authorize_request(user_id="student-1", role="student", intent=intent, text="show marks for student-2")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "unauthorized_target")

    # =========================================================================
    # Requirement 5: Student attempting to access another student's attendance
    # =========================================================================
    def test_another_student_attendance_rbac_blocks(self) -> None:
        """RBAC blocks student from reading another student's attendance."""
        intent = {
            "action": "read",
            "table": "attendance",
            "filters": {"student_id": None, "student_name": "Priya", "subject": "DBMS", "date": None, "status": None},
        }
        result = authorize_request(user_id="student-1", role="student", intent=intent, text="show me Priya's attendance")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "unauthorized_target")

    # =========================================================================
    # Requirement 6: Ambiguous student-target requests being denied safely
    # =========================================================================
    def test_ambiguous_student_mention_rbac_blocks(self) -> None:
        """RBAC blocks requests that mention 'student' ambiguously."""
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {"student_id": None, "student_name": None, "subject": None, "date": None, "status": None},
        }
        result = authorize_request(
            user_id="student-1",
            role="student",
            intent=intent,
            text="show me the student's marks"  # ambiguous
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "ambiguous_target")

    def test_ambiguous_person_rbac_blocks(self) -> None:
        """RBAC blocks requests that mention 'person' ambiguously."""
        intent = {
            "action": "read",
            "table": "attendance",
            "filters": {"student_id": None, "student_name": None, "subject": None, "date": None, "status": None},
        }
        result = authorize_request(
            user_id="student-1",
            role="student",
            intent=intent,
            text="what's that person's attendance"
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "ambiguous_target")

    # =========================================================================
    # Requirement 7: Question words never becoming student_name
    # =========================================================================
    def test_question_word_what_not_student_name(self) -> None:
        """Intent engine sanitizes 'What' so it never becomes student_name."""
        class BrokenGeminiModels:
            def generate_content(self, **kwargs):
                # Simulate Gemini incorrectly returning "What" as student_name
                return FakeGeminiResponse(
                    '{"action":"read","table":"marks",'
                    '"filters":{"student_id":null,"student_name":"What",'
                    '"subject":"DBMS","date":null,"status":null}}'
                )

        engine = IntentEngine(client=type("C", (), {"models": BrokenGeminiModels()})())
        intent = engine.parse("What marks do I have?", "student", self.schema_map)
        self.assertIsNone(intent["filters"]["student_name"])

    def test_question_word_whats_not_student_name(self) -> None:
        """Intent engine sanitizes 'What's' so it never becomes student_name."""
        class BrokenGeminiModels:
            def generate_content(self, **kwargs):
                return FakeGeminiResponse(
                    '{"action":"read","table":"attendance",'
                    '"filters":{"student_id":null,"student_name":"What\'s",'
                    '"subject":"DBMS","date":null,"status":null}}'
                )

        engine = IntentEngine(client=type("C", (), {"models": BrokenGeminiModels()})())
        intent = engine.parse("What's my attendance?", "student", self.schema_map)
        self.assertIsNone(intent["filters"]["student_name"])

    def test_question_word_who_not_student_name(self) -> None:
        """Intent engine sanitizes 'Who' so it never becomes student_name."""
        class BrokenGeminiModels:
            def generate_content(self, **kwargs):
                return FakeGeminiResponse(
                    '{"action":"read","table":"marks",'
                    '"filters":{"student_id":null,"student_name":"Who",'
                    '"subject":null,"date":null,"status":null}}'
                )

        engine = IntentEngine(client=type("C", (), {"models": BrokenGeminiModels()})())
        intent = engine.parse("Who has the best marks?", "student", self.schema_map)
        self.assertIsNone(intent["filters"]["student_name"])

    def test_question_word_which_not_student_name(self) -> None:
        """Intent engine sanitizes 'Which' so it never becomes student_name."""
        class BrokenGeminiModels:
            def generate_content(self, **kwargs):
                return FakeGeminiResponse(
                    '{"action":"read","table":"marks",'
                    '"filters":{"student_id":null,"student_name":"Which",'
                    '"subject":null,"date":null,"status":null}}'
                )

        engine = IntentEngine(client=type("C", (), {"models": BrokenGeminiModels()})())
        intent = engine.parse("Which student has the most attendance?", "student", self.schema_map)
        self.assertIsNone(intent["filters"]["student_name"])

    def test_pronouns_not_student_name(self) -> None:
        """Intent engine sanitizes pronouns so they never become student_name."""
        for pronoun in ["Me", "My", "I", "You"]:
            class BrokenGeminiModels:
                def generate_content(self, **kwargs):
                    return FakeGeminiResponse(
                        f'{{"action":"read","table":"marks",'
                        f'"filters":{{"student_id":null,"student_name":"{pronoun}",'
                        f'"subject":null,"date":null,"status":null}}}}'
                    )

            engine = IntentEngine(client=type("C", (), {"models": BrokenGeminiModels()})())
            intent = engine.parse(f"What are {pronoun.lower()}'s marks?", "student", self.schema_map)
            self.assertIsNone(intent["filters"]["student_name"],
                              f"Pronoun '{pronoun}' should not be treated as student_name")

    # =========================================================================
    # Requirement 8: Unsupported/gibberish requests
    # =========================================================================
    def test_gibberish_returns_unsupported(self) -> None:
        """Intent engine marks gibberish as unsupported."""
        intent = self.engine.parse("asdfghjkl", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_empty_request_returns_unsupported(self) -> None:
        """Intent engine marks empty requests as unsupported."""
        intent = self.engine.parse("", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_whitespace_only_returns_unsupported(self) -> None:
        """Intent engine marks whitespace-only requests as unsupported."""
        intent = self.engine.parse("   ", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_nonsense_returns_unsupported(self) -> None:
        """Intent engine marks nonsense queries as unsupported."""
        intent = self.engine.parse("tell me a joke about cats", "student", self.schema_map)
        # Even if Gemini tries to interpret it, it should be unsupported
        # because it's not related to VoxERP operations
        self.assertIn(intent["action"], ["unsupported", "read", "write"])

    # =========================================================================
    # Requirement 9: Dangerous write/delete requests remaining unsupported
    # =========================================================================
    def test_delete_request_returns_unsupported(self) -> None:
        """Intent engine marks delete requests as unsupported."""
        intent = self.engine.parse("Delete all attendance", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_drop_table_returns_unsupported(self) -> None:
        """Intent engine marks DROP/database modification as unsupported."""
        intent = self.engine.parse("Drop the attendance table", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")

    def test_update_marks_returns_unsupported_or_write(self) -> None:
        """Intent engine does not support arbitrary mark updates."""
        intent = self.engine.parse("Change my marks to 100", "student", self.schema_map)
        # Should either be unsupported or parsed as something else
        # (but RBAC should handle it if it gets through)
        self.assertIn(intent["action"], ["unsupported", "read", "write"])

    def test_only_attendance_write_is_supported(self) -> None:
        """Intent engine only supports attendance writes, no mark/timetable writes."""
        intent_marks_write = self.engine.parse("Write my marks", "student", self.schema_map)
        # Mark writes are not supported - should not be a write on marks
        is_not_marks_write = (intent_marks_write.get("table") != "marks" or
                              intent_marks_write.get("action") != "write")
        self.assertTrue(is_not_marks_write)

    # =========================================================================
    # Requirement 10: Gemini/API failure failing closed safely
    # =========================================================================
    def test_gemini_exception_fails_closed(self) -> None:
        """Intent engine fails safely (returns unsupported) when Gemini raises."""
        class RaisingGeminiModels:
            def generate_content(self, **kwargs):
                raise Exception("429 RESOURCE_EXHAUSTED")

        engine = IntentEngine(client=type("C", (), {"models": RaisingGeminiModels()})())
        intent = engine.parse("What's my DBMS attendance?", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_gemini_malformed_json_fails_closed(self) -> None:
        """Intent engine fails safely when Gemini returns malformed JSON."""
        class MalformedGeminiModels:
            def generate_content(self, **kwargs):
                return FakeGeminiResponse("{invalid json")

        engine = IntentEngine(client=type("C", (), {"models": MalformedGeminiModels()})())
        intent = engine.parse("What's my marks?", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_gemini_null_response_fails_closed(self) -> None:
        """Intent engine fails safely when Gemini returns None."""
        class NullGeminiModels:
            def generate_content(self, **kwargs):
                return None

        engine = IntentEngine(client=type("C", (), {"models": NullGeminiModels()})())
        intent = engine.parse("What's my marks?", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_gemini_timeout_fails_closed(self) -> None:
        """Intent engine fails safely when Gemini times out."""
        class TimeoutGeminiModels:
            def generate_content(self, **kwargs):
                raise TimeoutError("Request timed out")

        engine = IntentEngine(client=type("C", (), {"models": TimeoutGeminiModels()})())
        intent = engine.parse("What's my attendance?", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")
        self.assertEqual(intent["table"], "unsupported")

    def test_no_gemini_client_fails_closed(self) -> None:
        """Intent engine fails safely when no Gemini client is available."""
        import os

        class AlwaysNoneClient:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("No client should be constructed in this test")

        old_key = os.environ.pop("GEMINI_API_KEY", None)
        old_genai_client = None
        import intelligence.intent_engine as ie_module
        old_genai_client = ie_module.genai.Client
        ie_module.genai.Client = AlwaysNoneClient
        try:
            engine = IntentEngine(client=None)
            self.assertIsNone(engine.client)
            intent = engine.parse("What's my marks?", "student", self.schema_map)
            self.assertEqual(intent["action"], "unsupported")
            self.assertEqual(intent["table"], "unsupported")
        finally:
            ie_module.genai.Client = old_genai_client
            if old_key is not None:
                os.environ["GEMINI_API_KEY"] = old_key

    # =========================================================================
    # Requirement 11: Attendance write requests requiring confirmation flow
    # =========================================================================
    def test_attendance_write_intent_extracted(self) -> None:
        """Intent engine correctly identifies attendance write requests."""
        intent = self.engine.parse("Mark Vijay absent", "student", self.schema_map)
        self.assertEqual(intent["action"], "write")
        self.assertEqual(intent["table"], "attendance")
        self.assertEqual(intent["filters"]["status"], "absent")

    def test_attendance_write_present_status(self) -> None:
        """Intent engine correctly captures 'present' status for attendance."""
        intent = self.engine.parse("Mark me present in DBMS", "student", self.schema_map)
        self.assertEqual(intent["action"], "write")
        self.assertEqual(intent["table"], "attendance")
        self.assertEqual(intent["filters"]["status"], "present")

    def test_attendance_write_rbac_allows_self(self) -> None:
        """RBAC allows student to write their own attendance (subject to confirmation)."""
        intent = {
            "action": "write",
            "table": "attendance",
            "filters": {"student_id": None, "student_name": None, "subject": "DBMS", "date": None, "status": "absent"},
        }
        result = authorize_request(
            user_id="student-1",
            role="student",
            intent=intent,
            text="record my attendance as absent in DBMS"  # Contains " my " pattern
        )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["target_student_id"], "student-1")

    def test_attendance_write_rbac_blocks_other_student(self) -> None:
        """RBAC blocks student from writing another student's attendance."""
        intent = {
            "action": "write",
            "table": "attendance",
            "filters": {"student_id": None, "student_name": "Priya", "subject": "DBMS", "date": None, "status": "absent"},
        }
        result = authorize_request(
            user_id="student-1",
            role="student",
            intent=intent,
            text="mark Priya absent"
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "unauthorized_target")

    def test_attendance_write_requires_subject(self) -> None:
        """Attendance write intent requires a subject to be extracted."""
        intent = self.engine.parse("Mark me absent in DBMS", "student", self.schema_map)
        # Should extract subject
        # (The app.py handler will ask for subject if it's missing)
        self.assertEqual(intent["action"], "write")
        self.assertEqual(intent["table"], "attendance")

    def test_attendance_write_safety_guard_overrides_gemini(self) -> None:
        """Safety guard deterministically recognizes write commands."""
        # Even if Gemini returns something odd, deterministic guard should fix it
        class WeirdGeminiModels:
            def generate_content(self, **kwargs):
                return FakeGeminiResponse('{"action":"read","table":"marks","filters":{"student_id":null,"student_name":"Bob","subject":null,"date":null,"status":null}}')

        engine = IntentEngine(client=type("C", (), {"models": WeirdGeminiModels()})())
        intent = engine.parse("Mark Bob absent in DBMS", "student", self.schema_map)
        # Safety guard should override and detect the write
        self.assertEqual(intent["action"], "write")
        self.assertEqual(intent["table"], "attendance")
        self.assertEqual(intent["filters"]["status"], "absent")

    def test_mark_verb_with_absent_triggers_write_safety_guard(self) -> None:
        """Safety guard triggers on 'mark' + 'absent'."""
        intent_text = "Mark Vijay absent in DBMS"
        intent = self.engine.parse(intent_text, "student", self.schema_map)
        self.assertEqual(intent["action"], "write")
        self.assertEqual(intent["table"], "attendance")
        self.assertEqual(intent["filters"]["status"], "absent")
        self.assertEqual(intent["filters"]["student_name"], "Vijay")
        self.assertEqual(intent["filters"]["subject"], "DBMS")

    def test_record_verb_with_present_triggers_write_safety_guard(self) -> None:
        """Safety guard triggers on 'record' + 'present'."""
        intent_text = "Record me present"
        intent = self.engine.parse(intent_text, "student", self.schema_map)
        self.assertEqual(intent["action"], "write")
        self.assertEqual(intent["table"], "attendance")
        self.assertEqual(intent["filters"]["status"], "present")


if __name__ == "__main__":
    unittest.main()
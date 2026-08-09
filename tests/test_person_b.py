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
        if "mark vijay absent" in lowered or ("mark" in lowered and "absent" in lowered):
            return FakeGeminiResponse('{"action":"write","table":"attendance","filters":{"student_id":null,"student_name":"Vijay","subject":null,"date":null,"status":"absent"}}')
        if "weather" in lowered or "asdfghjkl" in lowered:
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
        self.assertEqual(teacher["reason"], "teacher_scope_unknown")

    def test_response_generator_handles_adapter_statuses(self) -> None:
        self.assertIn("no recorded", generate_response({"status": "no_data", "message": "No attendance recorded for DBMS"}))
        self.assertIn("couldn't find", generate_response({"status": "not_found", "message": "I couldn't find that subject"}))
        self.assertIn("already marked", generate_response({"status": "unchanged", "message": "Attendance already marked as absent"}))
        self.assertIn("marked", generate_response({"status": "created", "message": "Marked attendance for student-1"}))
        self.assertIn("updated", generate_response({"status": "updated", "message": "Updated attendance"}))


if __name__ == "__main__":
    unittest.main()
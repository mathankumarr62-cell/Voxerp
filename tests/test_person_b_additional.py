import os
import unittest
from intelligence.intent_engine import IntentEngine


class BrokenGeminiModels:
    def generate_content(self, **kwargs):
        # Simulate Gemini returning a student_name that's actually a question word
        return type("Resp", (), {"text": '{"action":"read","table":"attendance","filters":{"student_id":null,"student_name":"What","subject":"DBMS","date":null,"status":null}}'})()


class RaisingGeminiModels:
    def generate_content(self, **kwargs):
        raise Exception("429 RESOURCE_EXHAUSTED")


class AdditionalIntentTests(unittest.TestCase):
    def setUp(self):
        # Ensure offline mode from other tests does not affect these cases
        os.environ.pop("VOXERP_OFFLINE_MODE", None)

        # Use a minimal schema_map for parse requirements
        self.schema_map = {"tables": {}, "description": "test"}

    def test_gemini_question_word_not_treated_as_name(self):
        engine = IntentEngine(client=type("C", (), {"models": BrokenGeminiModels()})())
        intent = engine.parse("What's my DBMS attendance?", "student", self.schema_map)
        self.assertEqual(intent["table"], "attendance")
        self.assertIsNone(intent["filters"]["student_name"])  # question word must not be a name

    def test_ambiguous_dbms_attendance_does_not_guess_student(self):
        engine = IntentEngine(client=type("C", (), {"models": BrokenGeminiModels()})())
        intent = engine.parse("DBMS attendance", "student", self.schema_map)
        self.assertEqual(intent["table"], "attendance")
        self.assertIsNone(intent["filters"]["student_name"])

    def test_gemini_failure_falls_back_safely(self):
        # Simulate a Gemini API failure by providing a client whose model raises
        engine = IntentEngine(client=type("C", (), {"models": RaisingGeminiModels()})())
        intent = engine.parse("What's my DBMS attendance?", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")

    def test_dangerous_request_remains_unsupported(self):
        class DangerousReturningModels:
            def generate_content(self, **kwargs):
                prompt = kwargs.get("contents", "")
                if "delete" in prompt.lower():
                    return type("Resp", (), {"text": '{"action":"unsupported","table":"unsupported","filters":{"student_id":null,"student_name":null,"subject":null,"date":null,"status":null}}'})()
                return type("Resp", (), {"text": '{"action":"read","table":"attendance","filters":{"student_id":null,"student_name":null,"subject":"DBMS","date":null,"status":null}}'})()

        engine = IntentEngine(client=type("C", (), {"models": DangerousReturningModels()})())
        intent = engine.parse("Delete all attendance.", "student", self.schema_map)
        self.assertEqual(intent["action"], "unsupported")


if __name__ == "__main__":
    unittest.main()

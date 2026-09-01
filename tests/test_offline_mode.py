import os
import unittest
from unittest.mock import patch
import db_adapter

# Enable offline presentation mode for these tests before importing the app
os.environ["VOXERP_OFFLINE_MODE"] = "true"
import app as flask_app


class OfflineModeIntegrationTests(unittest.TestCase):
    def setUp(self):
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()
        db_adapter.initialize_database()

    def test_read_attendance_offline(self):
        response = self.client.post(
            "/query",
            json={"text": "What's my DBMS attendance?", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("Attendance for DBMS", data["reply_text"])

    def test_read_marks_offline(self):
        response = self.client.post(
            "/query",
            json={"text": "Tell me my DBMS marks.", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("Marks for DBMS", data["reply_text"])

    def test_timetable_offline(self):
        response = self.client.post(
            "/query",
            json={"text": "What is my timetable?", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("Timetable", data["reply_text"])

    def test_what_queries_do_not_extract_question_word_as_student_name_offline(self):
        engine = flask_app.intent_engine
        schema = db_adapter.build_schema_map()

        attendance_intent = engine.parse("What's my DBMS attendance?", "student", schema)
        self.assertEqual(attendance_intent["action"], "read")
        self.assertEqual(attendance_intent["table"], "attendance")
        self.assertIsNone(attendance_intent["filters"]["student_name"])
        self.assertEqual(attendance_intent["filters"]["subject"], "DBMS")

        marks_intent = engine.parse("What's my mark in DBMS?", "student", schema)
        self.assertEqual(marks_intent["action"], "read")
        self.assertEqual(marks_intent["table"], "marks")
        self.assertIsNone(marks_intent["filters"]["student_name"])
        self.assertEqual(marks_intent["filters"]["subject"], "DBMS")

    @patch("db_adapter.get_marks")
    def test_rbac_denies_other_student_offline(self, mock_get_marks):
        response = self.client.post(
            "/query",
            json={"text": "Show me Priya's marks", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["reply_text"], "You can only access your own data.")
        mock_get_marks.assert_not_called()

    @patch("db_adapter.get_marks")
    def test_ambiguous_target_denied_offline(self, mock_get_marks):
        response = self.client.post(
            "/query",
            json={"text": "Show me another student's marks", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["reply_text"], "You can only access your own data.")
        mock_get_marks.assert_not_called()

    @patch("db_adapter.mark_attendance")
    def test_write_flow_unauthorized_target_denied_offline(self, mock_mark):
        # Security hardening must deny cross-student writes before confirmation.
        response = self.client.post(
            "/query",
            json={"text": "Mark Vijay absent in DBMS", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["reply_text"], "You can only access your own data.")
        self.assertFalse(data.get("requires_confirmation", False))
        mock_mark.assert_not_called()

    def test_confirm_yes_executes_mark_attendance_offline(self):
        pending = {
            "student_id": "student-1",
            "subject": "DBMS",
            "date": "2026-08-10",
            "status": "absent",
            "actor_id": "student-1",
        }
        yes_res = self.client.post(
            "/confirm",
            json={"confirm": "yes", "pending": pending},
        )
        self.assertEqual(yes_res.status_code, 200)
        reply = yes_res.get_json()["reply_text"]
        self.assertTrue("marked" in reply.lower() or "updated" in reply.lower())

        conn = db_adapter._connect()
        try:
            row = conn.execute(
                "SELECT status FROM attendance WHERE student_id = ? AND subject = ? AND attendance_date = ?",
                ("student-1", "DBMS", "2026-08-10"),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["status"], "absent")
        finally:
            conn.close()

    def test_unsupported_and_gibberish_offline(self):
        resp = self.client.post(
            "/query",
            json={"text": "What's the weather today?", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("I can't help with that request", resp.get_json()["reply_text"])

        resp2 = self.client.post(
            "/query",
            json={"text": "asdfghjkl", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertIn("I can't help with that request", resp2.get_json()["reply_text"])


if __name__ == "__main__":
    unittest.main()

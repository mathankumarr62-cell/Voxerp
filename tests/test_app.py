import unittest
from unittest.mock import patch
import json
import app as flask_app
import db_adapter
from intelligence.intent_engine import IntentEngine


class TestGeminiModels:
    def generate_content(self, **kwargs):
        prompt = kwargs.get("contents", "")
        lowered = prompt.lower()

        if "priya" in lowered:
            return type("Resp", (), {"text": '{"action":"read","table":"marks","filters":{"student_id":null,"student_name":"Priya","subject":null,"date":null,"status":null}}'})()
        if "dbms attendance" in lowered:
            return type("Resp", (), {"text": '{"action":"read","table":"attendance","filters":{"student_id":null,"student_name":null,"subject":"DBMS","date":null,"status":null}}'})()
        if "mark vijay absent in dbms" in lowered:
            return type("Resp", (), {"text": '{"action":"write","table":"attendance","filters":{"student_id":null,"student_name":"Vijay","subject":"DBMS","date":null,"status":"absent"}}'})()
        if "mark vijay absent" in lowered:
            return type("Resp", (), {"text": '{"action":"write","table":"attendance","filters":{"student_id":null,"student_name":"Vijay","subject":null,"date":null,"status":"absent"}}'})()
        
        return type("Resp", (), {"text": '{"action":"read","table":"marks","filters":{"student_id":null,"student_name":null,"subject":null,"date":null,"status":null}}'})()


class AppIntegrationTests(unittest.TestCase):
    def setUp(self):
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()
        db_adapter.initialize_database()
        flask_app.intent_engine = IntentEngine(client=type("Client", (), {"models": TestGeminiModels()})())

    def test_student_read_own_attendance_success(self):
        response = self.client.post(
            "/query",
            json={"text": "What's my DBMS attendance?", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("Attendance for DBMS", data["reply_text"])

    @patch("db_adapter.get_marks")
    def test_student_read_other_marks_denied_without_db_adapter_call(self, mock_get_marks):
        response = self.client.post(
            "/query",
            json={"text": "Show me Priya's marks", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["reply_text"], "You can only access your own data.")
        mock_get_marks.assert_not_called()

    @patch("db_adapter.mark_attendance")
    def test_student_write_other_student_denied_without_db_adapter_call(self, mock_mark):
        response = self.client.post(
            "/query",
            json={"text": "Mark Vijay absent in DBMS", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["reply_text"], "You can only access your own data.")
        self.assertFalse(data.get("requires_confirmation", False))
        mock_mark.assert_not_called()

    def test_write_flow_without_subject_prompts_for_subject(self):
        response = self.client.post(
            "/query",
            json={"text": "Mark Vijay absent", "user_id": "student-1", "role": "student"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["reply_text"], "Which subject should I mark absent?")
        self.assertFalse(data.get("requires_confirmation", False))

    def test_confirm_yes_executes_mark_attendance(self):
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


if __name__ == "__main__":
    unittest.main()

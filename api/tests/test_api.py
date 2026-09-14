from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase

from api.views import PENDING_SALT


class ApiSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="student-1", password="safe-password")
        self.other_user = get_user_model().objects.create_user(username="student-2", password="safe-password")

    def test_api_requires_django_authentication(self):
        response = self.client.post("/api/query/", data='{"text":"my marks"}', content_type="application/json")
        self.assertEqual(response.status_code, 302)

    def test_invalid_json_is_rejected_after_login(self):
        self.client.force_login(self.user)
        response = self.client.post("/api/query/", data="not-json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid JSON", response.json()["reply_text"])

    @patch("api.views.service.confirm")
    @patch("api.views.service.query")
    def test_confirmation_is_signed_bound_to_user_and_single_use(self, query, confirm):
        query.return_value = {
            "status": 200, "reply_text": "Confirm", "requires_confirmation": True,
            "pending": {"student_id": "student-1", "subject": "DBMS", "date": "2026-01-01", "status": "absent", "period": 2},
        }
        confirm.return_value = {"status": 200, "reply_text": "Marked"}
        self.client.force_login(self.user)
        token = self.client.post("/api/query/", data='{"text":"mark me absent"}', content_type="application/json").json()["pending"]
        first = self.client.post("/api/confirm/", data={"confirm": "yes", "pending": token}, content_type="application/json")
        replay = self.client.post("/api/confirm/", data={"confirm": "yes", "pending": token}, content_type="application/json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(confirm.call_count, 1)

    @patch("api.views.service.confirm")
    @patch("api.views.service.query")
    def test_confirmation_no_is_signed_and_performs_no_write(self, query, confirm):
        query.return_value = {"status": 200, "reply_text": "Confirm", "requires_confirmation": True,
                              "pending": {"student_id": "student-1", "subject": "DBMS", "date": "2026-01-01", "status": "absent", "period": 2}}
        confirm.return_value = {"status": 200, "reply_text": "Okay, no changes made."}
        self.client.force_login(self.user)
        token = self.client.post("/api/query/", data='{"text":"mark me absent"}', content_type="application/json").json()["pending"]
        response = self.client.post("/api/confirm/", data={"confirm": "no", "pending": token}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.args[2], "no")

    def test_forged_and_other_user_confirmation_tokens_are_denied(self):
        payload = {"user_id": self.user.pk, "pending": {"student_id": "student-1", "subject": "DBMS", "date": "2026-01-01", "status": "absent", "period": 2}}
        token = signing.dumps(payload, salt=PENDING_SALT)
        self.client.force_login(self.other_user)
        other = self.client.post("/api/confirm/", data={"confirm": "yes", "pending": token}, content_type="application/json")
        self.assertEqual(other.status_code, 403)
        self.client.force_login(self.user)
        forged = self.client.post("/api/confirm/", data={"confirm": "yes", "pending": token + "tampered"}, content_type="application/json")
        self.assertEqual(forged.status_code, 400)

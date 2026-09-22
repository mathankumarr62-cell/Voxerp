from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import TestCase

from api.views import PENDING_SALT


class ApiSecurityTests(TestCase):
    def test_logout_returns_to_student_login(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post('/logout/'), '/login/')

    def test_undefined_privileged_roles_do_not_fall_back_to_student(self):
        from django.contrib.auth.models import Group
        from django.test import RequestFactory
        from api.views import _identity
        from intelligence.rbac import authorize_request

        request = RequestFactory().get('/')
        request.user = self.user
        for role in ('HOD', 'Admin'):
            with self.subTest(role=role):
                self.user.groups.set([Group.objects.create(name=role)])
                identity = _identity(request)
                self.assertEqual(identity.role, role.lower())
                decision = authorize_request(identity.user_id, identity.role,
                    {'action': 'read', 'table': 'marks', 'filters': {}}, 'Show my marks')
                self.assertFalse(decision['allowed'])
                self.assertEqual(decision['reason'], 'invalid_role')
        self.user.groups.clear()
        self.user.is_superuser = True
        self.assertEqual(_identity(request).role, 'admin')

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="student-1",
            password="safe-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="student-2",
            password="safe-password",
        )

    def test_api_requires_django_authentication(self):
        response = self.client.post(
            "/api/query/",
            data='{"text":"my marks"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

    def test_invalid_json_is_rejected_after_login(self):
        self.client.force_login(self.user)
        response = self.client.post(
            "/api/query/",
            data="not-json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid JSON", response.json()["reply_text"])

    @patch("api.views.service.confirm")
    @patch("api.views.service.query")
    def test_confirmation_is_signed_bound_to_user_and_single_use(self, query, confirm):
        query.return_value = {
            "status": 200,
            "reply_text": "Confirm",
            "requires_confirmation": True,
            "pending": {
                "student_id": "student-1",
                "subject": "DBMS",
                "date": "2026-01-01",
                "status": "absent",
                "period": 2,
            },
        }
        confirm.return_value = {"status": 200, "reply_text": "Marked"}

        self.client.force_login(self.user)
        response = self.client.post(
            "/api/query/",
            data='{"text":"mark me absent"}',
            content_type="application/json",
        )

        token = response.json()["pending"]

        first = self.client.post(
            "/api/confirm/",
            data={"confirm": "yes", "pending": token},
            content_type="application/json",
        )
        replay = self.client.post(
            "/api/confirm/",
            data={"confirm": "yes", "pending": token},
            content_type="application/json",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 409)
        confirm.assert_called_once()

    @patch("api.views.service.confirm")
    @patch("api.views.service.query")
    def test_confirmation_no_is_signed_and_performs_no_write(self, query, confirm):
        query.return_value = {
            "status": 200,
            "reply_text": "Confirm",
            "requires_confirmation": True,
            "pending": {
                "student_id": "student-1",
                "subject": "DBMS",
                "date": "2026-01-01",
                "status": "absent",
                "period": 2,
            },
        }
        confirm.return_value = {
            "status": 200,
            "reply_text": "Okay, no changes made.",
        }

        self.client.force_login(self.user)

        token = self.client.post(
            "/api/query/",
            data='{"text":"mark me absent"}',
            content_type="application/json",
        ).json()["pending"]

        response = self.client.post(
            "/api/confirm/",
            data={"confirm": "no", "pending": token},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        confirm.assert_called_once()
        self.assertEqual(confirm.call_args.args[2], "no")

    def test_forged_and_other_user_confirmation_tokens_are_denied(self):
        payload = {
            "user_id": self.user.pk,
            "pending": {
                "student_id": "student-1",
                "subject": "DBMS",
                "date": "2026-01-01",
                "status": "absent",
                "period": 2,
            },
        }

        token = signing.dumps(payload, salt=PENDING_SALT)

        self.client.force_login(self.other_user)

        other = self.client.post(
            "/api/confirm/",
            data={"confirm": "yes", "pending": token},
            content_type="application/json",
        )

        self.assertEqual(other.status_code, 403)

        self.client.force_login(self.user)

        forged = self.client.post(
            "/api/confirm/",
            data={"confirm": "yes", "pending": token + "tampered"},
            content_type="application/json",
        )

        self.assertEqual(forged.status_code, 400)


class ApiBusinessIntegrationTests(TestCase):
    """Django integration coverage for migrated VoxERP business behavior."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="student-1",
            password="safe-password",
        )
        self.other_user = get_user_model().objects.create_user(
            username="student-2",
            password="safe-password",
        )
        self.client.force_login(self.user)

    def _post_query(self, text):
        return self.client.post(
            "/api/query/",
            data={"text": text},
            content_type="application/json",
        )

    def _mock_engine(self, intent):
        class FakeIntentEngine:
            def parse(self, text, role, schema):
                return intent

        return FakeIntentEngine()

    def _use_engine(self, intent):
        from api.views import service

        original = service.engine
        service.engine = self._mock_engine(intent)
        return service, original

    def _restore_engine(self, service, original):
        service.engine = original

    def test_student_reads_own_attendance(self):
        intent = {
            "action": "read",
            "table": "attendance",
            "filters": {
                "student_id": None,
                "student_name": None,
                "subject": "DBMS",
                "date": None,
                "status": None,
            },
        }

        service, original = self._use_engine(intent)

        try:
            with patch(
                "api.services.db_adapter.get_attendance",
                return_value={
                    "status": "success",
                    "rows": [
                        {
                            "subject": "DBMS",
                            "attendance_date": "2026-08-20",
                            "status": "present",
                        }
                    ],
                    "message": "Attendance found.",
                },
            ) as get_attendance:
                response = self._post_query("What's my DBMS attendance?")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Attendance", response.json()["reply_text"])
        get_attendance.assert_called_once_with("student-1", "DBMS")

    def test_student_cannot_read_other_student_marks(self):
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {
                "student_id": None,
                "student_name": "student-2",
                "subject": None,
                "date": None,
                "status": None,
            },
        }

        service, original = self._use_engine(intent)

        try:
            with patch("api.services.db_adapter.get_marks") as get_marks:
                response = self._post_query("Show student-2's marks")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["reply_text"],
            "You can only access your own data.",
        )
        get_marks.assert_not_called()

    def test_student_cannot_write_for_other_student(self):
        intent = {
            "action": "write",
            "table": "attendance",
            "filters": {
                "student_id": None,
                "student_name": "student-2",
                "subject": "DBMS",
                "date": None,
                "status": "absent",
                "period": 2,
            },
        }

        service, original = self._use_engine(intent)

        try:
            with patch("api.services.db_adapter.mark_attendance") as mark_attendance:
                response = self._post_query("Mark student-2 absent in DBMS")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["reply_text"],
            "You can only access your own data.",
        )
        self.assertFalse(response.json().get("requires_confirmation", False))
        mark_attendance.assert_not_called()

    def test_write_without_subject_requests_subject(self):
        intent = {
            "action": "write",
            "table": "attendance",
            "filters": {
                "student_id": None,
                "student_name": None,
                "subject": None,
                "date": None,
                "status": "absent",
                "period": 2,
            },
        }

        service, original = self._use_engine(intent)

        try:
            response = self._post_query("Mark me absent")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json().get("requires_confirmation", False))
        self.assertIn("subject", response.json()["reply_text"].lower())

    def test_marks_read_reaches_adapter(self):
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {
                "student_id": None,
                "student_name": None,
                "subject": "DBMS",
                "date": None,
                "status": None,
            },
        }

        service, original = self._use_engine(intent)

        try:
            with patch(
                "api.services.db_adapter.get_marks",
                return_value={
                    "status": "success",
                    "rows": [
                        {
                            "assessment": "IAT 1",
                            "marks": 88,
                            "max_marks": 100,
                        }
                    ],
                    "message": "Marks found.",
                },
            ) as get_marks:
                response = self._post_query("Show my DBMS marks")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Marks", response.json()["reply_text"])
        get_marks.assert_called_once_with("student-1", "DBMS")

    def test_timetable_read_reaches_adapter(self):
        intent = {
            "action": "read",
            "table": "timetable",
            "filters": {
                "student_id": None,
                "student_name": None,
                "subject": None,
                "date": None,
                "status": None,
            },
        }

        service, original = self._use_engine(intent)

        try:
            with patch(
                "api.services.db_adapter.get_timetable",
                return_value={
                    "status": "success",
                    "rows": [
                        {
                            "day": "Monday",
                            "period": 1,
                            "subject": "DBMS",
                        }
                    ],
                    "message": "Timetable found.",
                },
            ) as get_timetable:
                response = self._post_query("What is my timetable?")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Timetable", response.json()["reply_text"])
        get_timetable.assert_called_once_with("student-1")

    def test_unsupported_request_is_handled(self):
        intent = {
            "action": "unsupported",
            "table": "unsupported",
            "filters": {},
        }

        service, original = self._use_engine(intent)

        try:
            response = self._post_query("What's the weather today?")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "I can't help with that request",
            response.json()["reply_text"],
        )

    def test_ambiguous_student_target_is_denied(self):
        intent = {
            "action": "read",
            "table": "marks",
            "filters": {
                "student_id": None,
                "student_name": None,
                "subject": None,
                "date": None,
                "status": None,
                "target": "another_student",
            },
        }

        service, original = self._use_engine(intent)

        try:
            with patch("api.services.db_adapter.get_marks") as get_marks:
                response = self._post_query("Show another student's marks")
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["reply_text"],
            "You can only access your own data.",
        )
        get_marks.assert_not_called()

    def test_confirmation_query_does_not_write_before_confirmation(self):
        intent = {
            "action": "write",
            "table": "attendance",
            "filters": {
                "student_id": None,
                "student_name": None,
                "subject": "DBMS",
                "date": "2026-09-14",
                "status": "absent",
                "period": 2,
            },
        }

        service, original = self._use_engine(intent)

        try:
            with patch("api.services.db_adapter.mark_attendance") as mark_attendance:
                response = self._post_query(
                    "Mark me absent in DBMS period 2"
                )
        finally:
            self._restore_engine(service, original)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["requires_confirmation"])
        self.assertIn("pending", response.json())

        mark_attendance.assert_not_called()

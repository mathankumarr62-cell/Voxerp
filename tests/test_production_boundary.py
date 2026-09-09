import os
import unittest
from unittest import mock

import app


class ProductionBoundaryTests(unittest.TestCase):
    def test_healthz_returns_only_a_generic_status(self):
        with mock.patch.object(app.db_adapter, "check_connection", return_value=False):
            response = app.app.test_client().get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"status": "unavailable"})

    def test_production_never_initializes_schema_even_if_requested(self):
        with mock.patch.dict(
            os.environ,
            {
                "VOXERP_ENV": "production",
                "VOXERP_INITIALIZE_DATABASE": "True",
                "VOXERP_USE_REAL_DB": "False",
            },
            clear=False,
        ):
            with mock.patch.object(app.db_adapter, "initialize_database") as initialize:
                app.bootstrap_application()
            initialize.assert_not_called()

    def test_proxy_mode_requires_a_trusted_proxy_and_group_role(self):
        with mock.patch.dict(
            os.environ,
            {
                "VOXERP_ENV": "production",
                "VOXERP_AUTH_MODE": "proxy",
                "VOXERP_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
                "VOXERP_ROLE_GROUPS": "college-students:student,college-teachers:teacher",
            },
            clear=False,
        ):
            client = app.app.test_client()
            blocked = client.get("/me")
            self.assertEqual(blocked.status_code, 401)

            authenticated = client.get(
                "/me",
                headers={
                    "X-Forwarded-User": "student-principal",
                    "X-Forwarded-Groups": "college-students",
                    "X-Forwarded-Student-Id": "123",
                },
            )
            self.assertEqual(authenticated.status_code, 200)
            self.assertEqual(authenticated.get_json(), {"user_id": "123", "role": "student"})

    def test_production_ignores_a_demo_auth_mode_override(self):
        with mock.patch.dict(
            os.environ,
            {
                "VOXERP_ENV": "production",
                "VOXERP_AUTH_MODE": "demo",
                "VOXERP_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
            },
            clear=False,
        ):
            response = app.app.test_client().post(
                "/query",
                json={"text": "show my timetable", "user_id": "forged", "role": "teacher"},
            )
            self.assertEqual(response.status_code, 401)
            self.assertIn("Authenticated user", response.get_json()["reply_text"])

    def test_proxy_confirmation_cannot_be_reused_by_another_identity(self):
        pending = {
            "student_id": "123",
            "subject": "DBMS",
            "date": "2099-12-31",
            "status": "absent",
            "actor_id": "teacher-principal",
            "actor_role": "teacher",
            "period": 1,
        }
        with mock.patch.dict(
            os.environ,
            {
                "VOXERP_ENV": "production",
                "VOXERP_AUTH_MODE": "proxy",
                "VOXERP_TRUSTED_PROXY_CIDRS": "127.0.0.1/32",
                "VOXERP_ROLE_GROUPS": "college-students:student,college-teachers:teacher",
                "VOXERP_PENDING_SECRET": "test-only-secret",
            },
            clear=False,
        ):
            token = app._confirmation_token(pending)
            response = app.app.test_client().post(
                "/confirm",
                json={"confirm": "yes", "confirmation_token": token},
                headers={
                    "X-Forwarded-User": "different-principal",
                    "X-Forwarded-Groups": "college-students",
                    "X-Forwarded-Student-Id": "123",
                },
            )
            self.assertEqual(response.status_code, 403)
            self.assertIn("different user", response.get_json()["reply_text"])


if __name__ == "__main__":
    unittest.main()

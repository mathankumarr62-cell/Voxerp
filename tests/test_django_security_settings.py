import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


ROOT = Path(__file__).resolve().parents[1]


def load_production_settings(overrides=None):
    environment = os.environ.copy()
    environment.update({
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "VOXERP_ENV": "production",
        "DJANGO_SECRET_KEY": "a" * 64,
        "DEBUG": "False",
        "ALLOWED_HOSTS": "erp.example.edu",
        "VOXERP_ALLOW_REAL_WRITES": "False",
    })
    environment.pop("VOXERP_TRUSTED_PROXY_SSL_HEADER", None)
    environment.update(overrides or {})
    code = (
        "import json; from django.conf import settings; "
        "print(json.dumps({"
        "'environment': settings.VOXERP_ENV, "
        "'debug': settings.DEBUG, "
        "'allowed_hosts': settings.ALLOWED_HOSTS, "
        "'ssl_redirect': settings.SECURE_SSL_REDIRECT, "
        "'hsts_seconds': settings.SECURE_HSTS_SECONDS, "
        "'session_cookie_secure': settings.SESSION_COOKIE_SECURE, "
        "'csrf_cookie_secure': settings.CSRF_COOKIE_SECURE, "
        "'proxy_ssl_header': settings.SECURE_PROXY_SSL_HEADER, "
        "'writes': settings.VOXERP_ALLOW_REAL_WRITES"
        "}))"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class DjangoSecuritySettingsTests(unittest.TestCase):
    def test_password_policy_rejects_common_and_numeric_passwords(self):
        user = get_user_model()(username="917")
        for password in ("password", "12345678"):
            with self.subTest(password=password), self.assertRaises(ValidationError):
                validate_password(password, user)

    def test_production_enforces_https_and_safe_defaults(self):
        result = load_production_settings()
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual(settings["environment"], "production")
        self.assertFalse(settings["debug"])
        self.assertEqual(settings["allowed_hosts"], ["erp.example.edu"])
        self.assertTrue(settings["ssl_redirect"])
        self.assertEqual(settings["hsts_seconds"], 31_536_000)
        self.assertTrue(settings["session_cookie_secure"])
        self.assertTrue(settings["csrf_cookie_secure"])
        self.assertIsNone(settings["proxy_ssl_header"])
        self.assertFalse(settings["writes"])

    def test_proxy_ssl_header_requires_explicit_trust_configuration(self):
        result = load_production_settings({"VOXERP_TRUSTED_PROXY_SSL_HEADER": "True"})
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads(result.stdout)
        self.assertEqual(settings["proxy_ssl_header"], ["HTTP_X_FORWARDED_PROTO", "https"])

    def test_missing_environment_defaults_to_production_and_typos_fail(self):
        result = load_production_settings({"VOXERP_ENV": ""})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["environment"], "production")

        typo = load_production_settings({"VOXERP_ENV": "prod"})
        self.assertNotEqual(typo.returncode, 0)
        self.assertIn("VOXERP_ENV must be explicitly set", typo.stderr)

    def test_production_rejects_unsafe_configuration(self):
        cases = (
            ({"DEBUG": "True"}, "Production requires DEBUG=False."),
            ({"ALLOWED_HOSTS": "localhost"}, "explicit nonlocal ALLOWED_HOSTS"),
            ({"VOXERP_ALLOW_REAL_WRITES": "True"}, "Production academic writes are disabled."),
            ({"VOXERP_SECURE_HSTS_SECONDS": "0"}, "requires a positive"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                result = load_production_settings(overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

"""Settings for the VoxERP application database (never the ERP database)."""
from pathlib import Path
import os
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

VOXERP_ENV = (os.getenv("VOXERP_ENV", "").strip().lower() or "production")
if VOXERP_ENV not in {"development", "production"}:
    raise ImproperlyConfigured("VOXERP_ENV must be explicitly set to development or production.")
IS_PRODUCTION = VOXERP_ENV == "production"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "unsafe-development-key-change-me")
if IS_PRODUCTION and (len(SECRET_KEY) < 32 or SECRET_KEY in {"unsafe-development-key-change-me", "replace-with-a-long-random-secret"}):
    raise ImproperlyConfigured("Production requires a configured random DJANGO_SECRET_KEY.")
DEBUG = os.getenv("DEBUG", "false").lower() in {"1", "true", "yes"}
if IS_PRODUCTION and DEBUG:
    raise ImproperlyConfigured("Production requires DEBUG=False.")
ALLOWED_HOSTS = [host.strip() for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if host.strip()]
if IS_PRODUCTION and (
    not ALLOWED_HOSTS
    or any(host.lower() in {"localhost", "127.0.0.1", "testserver", "*"} for host in ALLOWED_HOSTS)
):
    raise ImproperlyConfigured("Production requires explicit nonlocal ALLOWED_HOSTS.")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "core", "api",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "api" / "templates"], "APP_DIRS": True,
              "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# This database belongs solely to Django (auth, sessions and audit state).
# db_adapter.py independently connects to the read-only external ERP database.
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.getenv("VOXERP_APP_DB", str(BASE_DIR / "voxerp_app.sqlite3"))}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = IS_PRODUCTION
SECURE_HSTS_SECONDS = int(os.getenv(
    "VOXERP_SECURE_HSTS_SECONDS",
    "31536000" if IS_PRODUCTION else "0",
))
if IS_PRODUCTION and SECURE_HSTS_SECONDS <= 0:
    raise ImproperlyConfigured("Production requires a positive VOXERP_SECURE_HSTS_SECONDS.")
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv(
    "VOXERP_SECURE_HSTS_INCLUDE_SUBDOMAINS", "false"
).lower() in {"1", "true", "yes"}
SECURE_HSTS_PRELOAD = os.getenv("VOXERP_SECURE_HSTS_PRELOAD", "false").lower() in {
    "1", "true", "yes",
}
if SECURE_HSTS_PRELOAD and (
    not SECURE_HSTS_INCLUDE_SUBDOMAINS or SECURE_HSTS_SECONDS < 31_536_000
):
    raise ImproperlyConfigured(
        "HSTS preload requires at least one year and includeSubDomains."
    )
TRUSTED_PROXY_SSL_HEADER = os.getenv(
    "VOXERP_TRUSTED_PROXY_SSL_HEADER", "false"
).lower() in {"1", "true", "yes"}
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https") if TRUSTED_PROXY_SSL_HEADER else None
)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Kept explicit so test/development never accidentally enable real ERP writes.
VOXERP_ALLOW_REAL_WRITES = os.getenv("VOXERP_ALLOW_REAL_WRITES", "False").lower() in {"1", "true", "yes"}
if IS_PRODUCTION and VOXERP_ALLOW_REAL_WRITES:
    raise ImproperlyConfigured("Production academic writes are disabled.")

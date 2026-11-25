import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
# Local development reads the project .env. Containers ship without one, so
# App Service / CI environment variables are the only source there.
load_dotenv(BASE_DIR / ".env")


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


DEBUG = os.getenv("APP_ENV") == "development"
FRONTEND_PORT = env_int("FRONTEND_PORT", 5190)
ORIGIN = os.getenv("APP_ORIGIN", f"http://localhost:{FRONTEND_PORT}" if DEBUG else "")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
TOTP_ENCRYPTION_KEY = os.getenv("TOTP_ENCRYPTION_KEY", "")
BOOTSTRAP_INVITE_DIGEST = os.getenv("BOOTSTRAP_INVITE_DIGEST", "")

# Product parameters (see .env.example for meaning and defaults).
OWNER_SESSION_SECONDS = env_int("OWNER_SESSION_MINUTES", 240) * 60
PAIR_SECONDS = env_int("CONSULT_PAIR_MINUTES", 5) * 60
ACCESS_SECONDS = env_int("CONSULT_ACCESS_MINUTES", 45) * 60
INVITATION_HOURS = env_int("INVITATION_HOURS", 72)
ENROLLMENT_SECONDS = env_int("ENROLLMENT_MINUTES", 10) * 60
PDF_MAX_BYTES = env_int("PDF_MAX_MB", 20) * 1024 * 1024
SEALED_PDF_MAX_BYTES = PDF_MAX_BYTES + 29
EXAM_PAGE_SIZE = env_int("EXAM_PAGE_SIZE", 50)
PASSWORD_RESET_MINUTES = env_int("PASSWORD_RESET_MINUTES", 30)
# Ephemeral access policy (grants). Every lifetime is capped by GRANT_MAX_MINUTES.
GRANT_MAX_MINUTES = env_int("GRANT_MAX_MINUTES", 7 * 24 * 60)
LINK_VIEW_MINUTES = env_int("LINK_VIEW_MINUTES", 30)
LINK_PIN_MAX_FAILURES = env_int("LINK_PIN_MAX_FAILURES", 5)
HISTORY_WINDOW = env_int("HISTORY_WINDOW", 200)
SEALED_METADATA_MAX_BYTES = 2048
# Web Push (installable app). Generate with: python manage.py generate_vapid
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:contato@podeabrir.com").strip()

# Outbound email (SMTP, ported from agenda_ai). With EMAIL_ENABLED=false, development
# prints messages to the console instead and production refuses to start.
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "").strip()
EMAIL_SMTP_PORT = env_int("EMAIL_SMTP_PORT", 465)
EMAIL_SMTP_SECURITY = os.getenv("EMAIL_SMTP_SECURITY", "ssl").strip().lower()
EMAIL_SMTP_USERNAME = os.getenv("EMAIL_SMTP_USERNAME", "").strip()
EMAIL_SMTP_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "")
EMAIL_FROM_ADDRESS = os.getenv("EMAIL_FROM_ADDRESS", "").strip()
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Pode Abrir").strip()
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "").strip()
EMAIL_SMTP_TIMEOUT_SECONDS = env_int("EMAIL_SMTP_TIMEOUT_SECONDS", 20)
EMAIL_MAX_ATTEMPTS = env_int("EMAIL_MAX_ATTEMPTS", 3)
EMAIL_RETRY_BASE_SECONDS = env_int("EMAIL_RETRY_BASE_SECONDS", 60)
EMAIL_PROCESSING_TIMEOUT_SECONDS = env_int("EMAIL_PROCESSING_TIMEOUT_SECONDS", 120)
EMAIL_WORKER_INTERVAL_SECONDS = env_int("EMAIL_WORKER_INTERVAL_SECONDS", 3)
EMAIL_MAX_SENDS_PER_HOUR = env_int("EMAIL_MAX_SENDS_PER_HOUR", 5)
if not DEBUG and not EMAIL_ENABLED:
    raise ImproperlyConfigured("EMAIL_ENABLED=true é obrigatório em produção (convites e redefinição de senha).")

VAULT_NAMESPACE = os.getenv("VAULT_NAMESPACE", "pode-abrir-local" if DEBUG else "")
if not DEBUG and len(VAULT_NAMESPACE) < 32:
    raise ImproperlyConfigured("Configure VAULT_NAMESPACE com o valor de bootstrap_invite.")
origin = urlsplit(ORIGIN)
if (
    origin.scheme != ("http" if DEBUG else "https")
    or not origin.hostname
    or origin.username is not None
    or origin.path
    or origin.query
    or origin.fragment
):
    raise ImproperlyConfigured("APP_ORIGIN deve ser uma origem sem caminho ou barra final.")
if not DEBUG and len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Configure DJANGO_SECRET_KEY com pelo menos 50 caracteres.")
SECRET_KEY = SECRET_KEY or "django-insecure-local-development-never-use-in-production"
ALLOWED_HOSTS = [origin.hostname]
if not DEBUG:
    # App Service checks container startup separately from the public health check.
    # Let Django accept the name of the App Service as well as the configured domain.
    azure_host = os.getenv("WEBSITE_HOSTNAME")
    if azure_host:
        ALLOWED_HOSTS.append(azure_host)
CSRF_TRUSTED_ORIGINS = [ORIGIN]
ROOT_URLCONF = "exams.urls"
WSGI_APPLICATION = "exams.wsgi.application"

INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "exams",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "exams.security.PrivateResponseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# The React build (frontend/dist) is served from the site root by WhiteNoise;
# exams.spa answers every client-side route with its index.html.
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"
STATIC_URL = "/static/"
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.is_dir() else None
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MIMETYPES = {".webmanifest": "application/manifest+json"}

USE_TZ = True
TIME_ZONE = "America/Sao_Paulo"
LANGUAGE_CODE = "pt-br"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 128 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 1
FILE_UPLOAD_HANDLERS = [
    "exams.uploads.PDFSizeLimit",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]

SESSION_COOKIE_NAME = "owner_session" if DEBUG else "__Host-owner_session"
READER_COOKIE_NAME = "reader_session" if DEBUG else "__Host-reader_session"
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = OWNER_SESSION_SECONDS
# The SPA receives the CSRF token from GET /api/session/, so the cookie stays HttpOnly.
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_NAME = "csrf" if DEBUG else "__Host-csrf"
CSRF_FAILURE_VIEW = "exams.responses.csrf_failure"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if not DEBUG else None
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_REFERRER_POLICY = "same-origin"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "exams.audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "exams.outbox": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}


def postgres(host: str, port: str, name: str, user: str, password: str, sslmode: str) -> dict:
    return {
        "ENGINE": "django.db.backends.postgresql",
        "HOST": host,
        "PORT": port,
        "NAME": name,
        "USER": user,
        "PASSWORD": password,
        "OPTIONS": {
            "sslmode": sslmode,
            "sslrootcert": os.getenv("POSTGRES_SSLROOTCERT", "/etc/ssl/certs/ca-certificates.crt"),
            "connect_timeout": 5,
        },
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }


if os.getenv("POSTGRES_HOST"):
    # Azure / CI. TLS is mandatory outside development.
    DATABASES = {"default": postgres(
        os.environ["POSTGRES_HOST"], os.getenv("POSTGRES_PORT", "5432"), os.environ["POSTGRES_DB"],
        os.environ["POSTGRES_USER"], os.environ["POSTGRES_PASSWORD"],
        "verify-full" if not DEBUG else os.getenv("POSTGRES_SSLMODE", "disable"),
    )}
elif DEBUG:
    # Development: the shared local container (agenda_ai_local_pg). Only PG_LOCAL_DATABASE is
    # used (positron_db; positron_e2e for disposable browser-test runs). PostgreSQL everywhere.
    DATABASES = {"default": postgres(
        os.getenv("PG_LOCAL_HOST", "localhost"), os.getenv("PG_LOCAL_PORT", "5432"),
        os.environ["PG_LOCAL_DATABASE"], os.environ["PG_LOCAL_USER"], os.environ["PG_LOCAL_PASSWORD"],
        os.getenv("PG_LOCAL_SSLMODE", "disable"),
    )}
else:
    raise ImproperlyConfigured("Configure POSTGRES_HOST e POSTGRES_* (PostgreSQL) fora do ambiente de desenvolvimento.")

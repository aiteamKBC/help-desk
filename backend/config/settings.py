import sys
from pathlib import Path

from .env import BASE_DIR, build_database_config, get_env, get_env_bool, get_env_list

SECRET_KEY = get_env("DJANGO_SECRET_KEY", "django-insecure-support-portal-dev-key")
DEBUG = get_env_bool("DJANGO_DEBUG", True)
DJANGO_ENV = (get_env("DJANGO_ENV", "development") or "development").strip().lower()
IS_PRODUCTION_LIKE = DJANGO_ENV == "production" or not DEBUG
IS_RUNSERVER = any(arg.startswith("runserver") for arg in sys.argv[1:])
LOCAL_ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
LOCAL_CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
]

ALLOWED_HOSTS = get_env_list("DJANGO_ALLOWED_HOSTS", ",".join(LOCAL_ALLOWED_HOSTS))
if IS_RUNSERVER:
    ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, *LOCAL_ALLOWED_HOSTS]))

CSRF_TRUSTED_ORIGINS = get_env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if IS_RUNSERVER:
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys([*CSRF_TRUSTED_ORIGINS, *LOCAL_CSRF_TRUSTED_ORIGINS]))
SUPPORT_ADMIN_SESSION_COOKIE_AGE = max(int(get_env("SUPPORT_ADMIN_SESSION_COOKIE_AGE_SECONDS", "300") or "300"), 60)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "support_portal",
    "knowledge_base",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = build_database_config(
    get_env("DATABASE_URL"),
    require_database_url=IS_PRODUCTION_LIKE,
    require_postgresql=IS_PRODUCTION_LIKE,
)

LANGUAGE_CODE = "en-us"
TIME_ZONE = get_env("TIME_ZONE", "Africa/Cairo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
SUPPORT_ATTACHMENT_ROOT = BASE_DIR / "media" / "support_attachments"
SUPPORT_ATTACHMENT_MAX_FILE_BYTES = max(
    int(get_env("SUPPORT_ATTACHMENT_MAX_FILE_BYTES", str(25 * 1024 * 1024)) or str(25 * 1024 * 1024)),
    1024,
)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
APPEND_SLASH = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_SAVE_EVERY_REQUEST = True

SUPPORT_PORTAL_PASSWORD = get_env("SUPPORT_PORTAL_PASSWORD")
BOOKING_WEBHOOK_URL = get_env("N8N_BOOKING_WEBHOOK_URL")
CHATBOT_WEBHOOK_URL = get_env("N8N_CHATBOT_WEBHOOK_URL")
ADMIN_AI_WEBHOOK_URL = get_env("N8N_ADMIN_AI_WEBHOOK_URL")
MAIL_WEBHOOK_URL = get_env("N8N_MAIL_WEBHOOK_URL")
SUPPORT_NOTIFICATION_WEBHOOK_URL = get_env(
    "N8N_SUPPORT_NOTIFICATION_WEBHOOK_URL",
    get_env("SUPPORT_NOTIFICATION_WEBHOOK_URL", ""),
)
COVERAGE_TICKET_WEBHOOK_URL = get_env(
    "N8N_COVERAGE_TICKET_WEBHOOK_URL",
    get_env("N8N_COVERAGE_OPERATIONS_WEBHOOK_URL", ""),
)
COVERAGE_SLA_WEBHOOK_URL = get_env(
    "N8N_COVERAGE_SLA_WEBHOOK_URL",
    COVERAGE_TICKET_WEBHOOK_URL,
)
COVERAGE_TUTOR_RESPONSE_MAIL_WEBHOOK_URL = get_env(
    "N8N_RESPONSE_MAIL_WEBHOOK_URL",
    get_env("N8N_ResponseMAIL_WEBHOOK_URL", ""),
)
SUPPORT_PORTAL_PUBLIC_BASE_URL = get_env("SUPPORT_PORTAL_PUBLIC_BASE_URL", "https://technicalsupport.kentbusinesscollege.net")
LEGACY_DATABASE_URL = get_env("LEGACY_DATABASE_URL")
KBC_AUTH_DATABASE_URL = get_env("KBC_AUTH_DATABASE_URL")
COMMUNICATION_CENTRE_DATABASE_URL = get_env("COMMUNICATION_CENTRE_DATABASE_URL")
LEGACY_EXPRESS_ENTRYPOINT = BASE_DIR / "index.mjs"
AZURE_BOOKING_TENANT_ID = get_env("AZURE_BOOKING_TENANT_ID", get_env("AZURE_TENANT_ID"))
AZURE_BOOKING_CLIENT_ID = get_env("AZURE_BOOKING_CLIENT_ID", get_env("AZURE_CLIENT_ID"))
AZURE_BOOKING_CLIENT_SECRET = get_env("AZURE_BOOKING_CLIENT_SECRET", get_env("AZURE_CLIENT_SECRET"))
AZURE_LOGIN_TENANT_ID = get_env("AZURE_LOGIN_TENANT_ID", get_env("AZURE_TENANT_ID"))
AZURE_LOGIN_CLIENT_ID = get_env("AZURE_LOGIN_CLIENT_ID", get_env("AZURE_CLIENT_ID"))
AZURE_LOGIN_CLIENT_SECRET = get_env("AZURE_LOGIN_CLIENT_SECRET", get_env("AZURE_CLIENT_SECRET"))
AZURE_LOGIN_REDIRECT_URI = get_env("AZURE_LOGIN_REDIRECT_URI")
AZURE_LOGIN_ALLOW_ANY_DIRECTORY_ROLE = get_env_bool("AZURE_LOGIN_ALLOW_ANY_DIRECTORY_ROLE", True)
AZURE_LOGIN_ADMIN_DIRECTORY_ROLES = get_env_list("AZURE_LOGIN_ADMIN_DIRECTORY_ROLES", "")
AZURE_LOGIN_SUPERADMIN_DIRECTORY_ROLES = get_env_list(
    "AZURE_LOGIN_SUPERADMIN_DIRECTORY_ROLES",
    "Global Administrator,Privileged Role Administrator",
)
BOOKING_BUSINESS_ID = get_env("BOOKING_BUSINESS_ID")
BOOKING_SERVICE_ID = get_env("BOOKING_SERVICE_ID")
SUPPORT_SESSION_DURATION_MINUTES = max(int(get_env("SUPPORT_SESSION_DURATION_MINUTES", "60") or "60"), 15)
SUPPORT_SESSION_SLOT_INTERVAL_MINUTES = max(int(get_env("SUPPORT_SESSION_SLOT_INTERVAL_MINUTES", "30") or "30"), 5)
SUPPORT_TEAMS_CALL_URL = get_env("SUPPORT_TEAMS_CALL_URL")
SUPPORT_TEAMS_CALL_TARGETS = get_env_list("SUPPORT_TEAMS_CALL_TARGETS", "")
SUPPORT_TEAMS_CALL_LABEL = get_env("SUPPORT_TEAMS_CALL_LABEL", "")
SUPPORT_BOOKING_URL = get_env(
    "SUPPORT_BOOKING_URL",
    "https://outlook.office.com/book/StudentSupport1@kentbusinesscollege.com/s/Z4Zc9rZxw0mEOB417C5bVQ2",
)
KNOWLEDGE_BASE_ROOT = Path(get_env("KNOWLEDGE_BASE_ROOT", str(BASE_DIR.parent / "Knowledge_Base_Builder")))

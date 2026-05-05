from pathlib import Path

from .env import BASE_DIR, build_database_config, get_env, get_env_bool, get_env_list

SECRET_KEY = get_env("DJANGO_SECRET_KEY", "django-insecure-support-portal-dev-key")
DEBUG = get_env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = get_env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver")
CSRF_TRUSTED_ORIGINS = get_env_list("DJANGO_CSRF_TRUSTED_ORIGINS", "")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "support_portal",
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

DATABASES = build_database_config(get_env("DATABASE_URL"))

LANGUAGE_CODE = "en-us"
TIME_ZONE = get_env("TIME_ZONE", "Africa/Cairo")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
APPEND_SLASH = True

SUPPORT_PORTAL_PASSWORD = get_env("SUPPORT_PORTAL_PASSWORD")
BOOKING_WEBHOOK_URL = get_env("N8N_BOOKING_WEBHOOK_URL")
CHATBOT_WEBHOOK_URL = get_env("N8N_CHATBOT_WEBHOOK_URL")
LEGACY_DATABASE_URL = get_env("LEGACY_DATABASE_URL")
LEGACY_EXPRESS_ENTRYPOINT = BASE_DIR / "index.mjs"
SUPPORT_SESSION_DURATION_MINUTES = max(int(get_env("SUPPORT_SESSION_DURATION_MINUTES", "60") or "60"), 15)

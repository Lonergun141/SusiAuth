import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[4]  # project root
# SKIP_DOTENV lets tests reload settings without .env repopulating env vars.
if os.getenv("SKIP_DOTENV") != "1":
    load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret")
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "anymail",
    "authsvc.apps.accounts",
    "authsvc.apps.tokens",
    "authsvc.apps.notifications",
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

ROOT_URLCONF = "authsvc.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "authsvc.config.wsgi.application"
ASGI_APPLICATION = "authsvc.config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "authdb"),
        "USER": os.getenv("DB_USER", "authuser"),
        "PASSWORD": os.getenv("DB_PASSWORD", "authpass"),
        "HOST": os.getenv("DB_HOST", "db"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email -------------------------------------------------------------------
# EMAIL_PROVIDER selects the delivery channel. "console" prints to the terminal
# (dev), "resend" delivers via Anymail's Resend backend, "smtp" uses the
# EMAIL_HOST_* settings. Resend-specific code lives in apps/notifications.
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console")
if EMAIL_PROVIDER == "resend":
    EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
elif EMAIL_PROVIDER == "console":
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
elif EMAIL_PROVIDER == "inmemory":
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
else:
    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@susiauth.local")

ANYMAIL = {"RESEND_API_KEY": os.getenv("RESEND_API_KEY", "")}
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", DEFAULT_FROM_EMAIL)
RESEND_WEBHOOK_SECRET = os.getenv("RESEND_WEBHOOK_SECRET", "")
EMAIL_DELIVERY_ENABLED = os.getenv("EMAIL_DELIVERY_ENABLED", "1") == "1"

# --- Celery ------------------------------------------------------------------
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "") or None
# Run tasks inline (no broker) when true — used in dev/test.
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") == "1"
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_SOFT_TIME_LIMIT = 90
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

JWT_ISSUER = os.getenv("JWT_ISSUER", "auth-service")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "your-apps")
JWT_ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "600"))
JWT_REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL_SECONDS", "2592000"))
OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "5"))
ONETIMETOKEN_TTL_MINUTES = int(os.getenv("ONETIMETOKEN_TTL_MINUTES", "15"))
JWT_PRIVATE_KEY_PATH = os.getenv("JWT_PRIVATE_KEY_PATH", str(BASE_DIR / "keys/jwt_private.pem"))
JWT_PUBLIC_KEY_PATH = os.getenv("JWT_PUBLIC_KEY_PATH", str(BASE_DIR / "keys/jwt_public.pem"))

FRONTEND_RESET_PASSWORD_URL = os.getenv("FRONTEND_RESET_PASSWORD_URL", "http://localhost/reset-password?token={token}")
FRONTEND_VERIFY_EMAIL_URL = os.getenv("FRONTEND_VERIFY_EMAIL_URL", "http://localhost/verify-email?token={token}")

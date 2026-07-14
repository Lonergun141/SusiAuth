"""Production settings.

Fails fast on import when required configuration is missing or insecure, so a
misconfigured deployment never boots serving traffic with dev defaults.
Secret values are never printed during validation.
"""
import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403

DEBUG = False


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- Secrets & hosts ---------------------------------------------------------
SECRET_KEY = _require("DJANGO_SECRET_KEY")
if SECRET_KEY == "dev-secret":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must not be the development default in production.")

ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list explicit hostnames in production (no wildcard)."
    )

# --- JWT signing keys must exist ---------------------------------------------
for _label, _path in (
    ("JWT_PRIVATE_KEY_PATH", JWT_PRIVATE_KEY_PATH),  # noqa: F405
    ("JWT_PUBLIC_KEY_PATH", JWT_PUBLIC_KEY_PATH),  # noqa: F405
):
    if not os.path.exists(_path):
        raise ImproperlyConfigured(f"{_label} points at a missing file: {_path}")

# --- Frontend URLs must be explicit and non-local ----------------------------
for _label in ("FRONTEND_RESET_PASSWORD_URL", "FRONTEND_VERIFY_EMAIL_URL"):
    _url = globals().get(_label, "")
    if "localhost" in _url or _url.startswith("http://localhost"):
        raise ImproperlyConfigured(f"{_label} must be an explicit production URL, not localhost.")

# --- Email provider ----------------------------------------------------------
# When Resend is the provider, its API key and webhook secret are mandatory.
if os.getenv("EMAIL_PROVIDER", "console") == "resend":
    _require("RESEND_API_KEY")
    _require("RESEND_WEBHOOK_SECRET")

# --- HTTPS / proxy -----------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = _bool("SECURE_SSL_REDIRECT", True)

# --- HSTS --------------------------------------------------------------------
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = _bool("SECURE_HSTS_PRELOAD", True)

# --- Headers -----------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Cookies -----------------------------------------------------------------
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

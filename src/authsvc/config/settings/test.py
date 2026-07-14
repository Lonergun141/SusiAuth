"""Test settings.

Defaults to an in-memory SQLite database for fast, dependency-free unit tests.
Set ``TEST_DATABASE=postgres`` (and the usual ``DB_*`` env vars) to run the
suite against PostgreSQL instead — required for the refresh-rotation
concurrency test, which relies on ``select_for_update`` row locking. CI does
this via a Postgres service container.
"""
import os

from .base import *  # noqa

DEBUG = False

if os.getenv("TEST_DATABASE") != "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

# Capture mail via the in-memory provider; run Celery tasks inline.
EMAIL_PROVIDER = "inmemory"
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Rate limiting depends on a shared cache and would interfere with rapid test
# calls; disable it so tests exercise business logic, not throttling.
RATELIMIT_ENABLE = False

# Fast password hashing for tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

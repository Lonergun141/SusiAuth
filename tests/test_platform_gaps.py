"""Regression tests for the final production-readiness gaps."""

import os
from pathlib import Path

import pytest


def test_first_party_api_is_canonical_under_v1(client):
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/health").status_code == 404


def test_runtime_cache_is_redis_backed():
    from authsvc.config.settings import base

    cache = base.CACHES["default"]
    assert cache["BACKEND"] == "django_redis.cache.RedisCache"
    assert cache["LOCATION"].endswith("/1")


def test_test_cache_remains_dependency_free(settings):
    assert settings.CACHES["default"]["BACKEND"].endswith("LocMemCache")


@pytest.mark.skipif(os.getenv("TEST_REDIS") != "1", reason="requires Redis integration service")
def test_two_cache_clients_share_distributed_rate_limit_state(settings):
    from django.core.cache import caches

    backend = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.getenv("REDIS_CACHE_URL", "redis://localhost:6379/1"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
    settings.CACHES = {"rate_limit_a": backend, "rate_limit_b": backend}
    cache_a = caches["rate_limit_a"]
    cache_b = caches["rate_limit_b"]
    cache_a.clear()

    cache_a.set("rate-limit/shared-key", 1, timeout=60)

    assert cache_b.incr("rate-limit/shared-key") == 2


def test_ci_builds_the_production_image():
    workflow = Path(".github/workflows/ci.yml").read_text()
    assert "docker/build-push-action" in workflow
    assert "push: false" in workflow


def test_docker_build_context_excludes_secrets_and_local_state():
    ignored = set(Path(".dockerignore").read_text().splitlines())
    assert {".env", ".git", ".venv", "keys/*"} <= ignored


@pytest.mark.django_db
def test_resend_backend_sends_idempotency_as_http_header(settings):
    from django.core.mail import EmailMultiAlternatives

    from authsvc.apps.notifications.resend_backend import EmailBackend

    settings.ANYMAIL = {"RESEND_API_KEY": "re_test"}
    message = EmailMultiAlternatives(
        subject="Security notice",
        body="body",
        from_email="from@example.com",
        to=["to@example.com"],
    )
    message.resend_idempotency_key = "password-changed/event-id"

    payload = EmailBackend().build_message_payload(message, {})

    assert payload.headers["Idempotency-Key"] == "password-changed/event-id"
    assert "Idempotency-Key" not in payload.data.get("headers", {})

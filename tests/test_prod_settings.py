"""Production settings must fail fast on missing/insecure config.

The prod settings module validates at import time, so we drive it by reloading
the module under different environments. The autouse ``jwt_keys`` fixture puts
valid signing-key paths in the environment, so these tests exercise the
secret/host/frontend guards rather than the key-existence guard.
"""
import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

PROD = "authsvc.config.settings.prod"


def _load_prod():
    # Reload base first so it re-reads the environment (a plain `from .base
    # import *` on the prod module would otherwise reuse base's already-computed
    # values, e.g. the default JWT key paths).
    import authsvc.config.settings.base as base

    importlib.reload(base)
    if PROD in sys.modules:
        return importlib.reload(sys.modules[PROD])
    return importlib.import_module(PROD)


def _valid_env(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "prod-secret-value-not-default")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "auth.example.com")
    monkeypatch.setenv("FRONTEND_RESET_PASSWORD_URL", "https://app.example.com/reset?token={token}")
    monkeypatch.setenv("FRONTEND_VERIFY_EMAIL_URL", "https://app.example.com/verify?token={token}")


def test_missing_secret_key_fails(monkeypatch):
    _valid_env(monkeypatch)
    monkeypatch.delenv("DJANGO_SECRET_KEY", raising=False)
    with pytest.raises(ImproperlyConfigured):
        _load_prod()


def test_dev_secret_key_rejected(monkeypatch):
    _valid_env(monkeypatch)
    monkeypatch.setenv("DJANGO_SECRET_KEY", "dev-secret")
    with pytest.raises(ImproperlyConfigured):
        _load_prod()


def test_wildcard_allowed_hosts_rejected(monkeypatch):
    _valid_env(monkeypatch)
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "*")
    with pytest.raises(ImproperlyConfigured):
        _load_prod()


def test_missing_allowed_hosts_fails(monkeypatch):
    _valid_env(monkeypatch)
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "")
    with pytest.raises(ImproperlyConfigured):
        _load_prod()


def test_localhost_frontend_url_rejected(monkeypatch):
    _valid_env(monkeypatch)
    monkeypatch.setenv("FRONTEND_VERIFY_EMAIL_URL", "http://localhost/verify?token={token}")
    with pytest.raises(ImproperlyConfigured):
        _load_prod()


def test_valid_env_enables_security_hardening(monkeypatch):
    _valid_env(monkeypatch)
    prod = _load_prod()

    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["auth.example.com"]
    assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SECURE_HSTS_SECONDS > 0
    assert prod.SECURE_CONTENT_TYPE_NOSNIFF is True
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.SESSION_COOKIE_HTTPONLY is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.X_FRAME_OPTIONS == "DENY"


@pytest.fixture(autouse=True)
def _restore_prod_module():
    """Reload prod under the test env, then drop it so other tests aren't
    affected by whatever env this test left it loaded with."""
    yield
    sys.modules.pop(PROD, None)

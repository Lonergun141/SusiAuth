"""Smoke tests: the API surface imports and wires up cleanly."""


def test_api_imports():
    from authsvc.api.v1.api import api_v1

    assert api_v1 is not None


def test_auth_router_imports():
    # Guards against the missing django-ratelimit regression (import-time failure).
    from authsvc.api.v1.routers import auth

    assert auth.router is not None

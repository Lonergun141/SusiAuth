"""Health/liveness/readiness probe tests."""
import pytest


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_liveness(client):
    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.django_db
def test_readiness_ok(client):
    # jwt_keys fixture (autouse) guarantees signing keys exist; the test DB is up.
    resp = client.get("/api/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["signing_key"] == "ok"

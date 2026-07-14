from django.db import connection
from django.http import JsonResponse
from ninja import Router

router = Router()


@router.get("")
def health(request):
    """Basic health check (backwards-compatible)."""
    return {"status": "ok"}


@router.get("/live")
def live(request):
    """Liveness probe — is the process up? No dependency checks."""
    return {"status": "alive"}


@router.get("/ready")
def ready(request):
    """Readiness probe — can we actually serve traffic?

    Checks the database connection and that JWT signing keys are present and
    loadable. Does not call out to external services (e.g. email providers).
    Returns 503 when any dependency is unavailable.
    """
    checks = {}
    ok = True

    try:
        connection.ensure_connection()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        ok = False

    try:
        from authsvc.apps.common.security import get_jwks

        get_jwks()
        checks["signing_key"] = "ok"
    except Exception:
        checks["signing_key"] = "error"
        ok = False

    body = {"status": "ready" if ok else "not_ready", "checks": checks}
    if not ok:
        return JsonResponse(body, status=503)
    return body

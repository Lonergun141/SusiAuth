"""Small, synchronous API for recording sanitized audit events."""

import uuid
from collections.abc import Mapping

from .models import AuditEvent

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "code",
    "credential",
    "jwt",
    "password",
    "secret",
    "token",
)


def _sanitize(value):
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
                else _sanitize(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _identity(value, fallback_type: str) -> tuple[str, str]:
    if value is None:
        return fallback_type, ""
    if isinstance(value, tuple):
        return str(value[0]), str(value[1])
    for attr, identity_type in (
        ("uuid", "user"),
        ("session_id", "session"),
        ("client_id", "oauth_client"),
        ("pk", fallback_type),
    ):
        identifier = getattr(value, attr, None)
        if identifier is not None:
            return identity_type, str(identifier)
    return fallback_type, str(value)


def _request_context(request) -> tuple[str, str | None, str]:
    if request is None:
        return "", None, ""
    request_id = request.META.get("HTTP_X_REQUEST_ID") or getattr(
        request, "_audit_request_id", ""
    )
    if not request_id:
        request_id = str(uuid.uuid4())
        request._audit_request_id = request_id
    return (
        str(request_id)[:64],
        request.META.get("REMOTE_ADDR"),
        request.META.get("HTTP_USER_AGENT", "")[:512],
    )


def record_event(
    event_type: str,
    *,
    result: str = AuditEvent.Result.SUCCESS,
    actor=None,
    target=None,
    request=None,
    metadata: dict | None = None,
) -> AuditEvent:
    """Persist one immutable event without retaining secrets or raw tokens."""
    actor_type, actor_id = _identity(actor, "anonymous")
    target_type, target_id = _identity(target, "object")
    request_id, ip_address, user_agent = _request_context(request)
    return AuditEvent.objects.create(
        event_type=event_type,
        result=result,
        actor_type=actor_type,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=_sanitize(metadata or {}),
    )

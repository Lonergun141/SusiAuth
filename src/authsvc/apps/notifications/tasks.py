"""Celery task that actually delivers an outbound email.

Sensitive content (codes/links) is rendered in the web process and passed to
the task transiently — it is never persisted on OutboundEmail and never logged.
"""
import random

from celery import shared_task
from django.utils import timezone

from authsvc.apps.audit.models import AuditEvent
from authsvc.apps.audit.services import record_event

from .models import OutboundEmail
from .providers import EmailMessageData, get_email_provider

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    try:
        import requests

        if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
            return True
    except Exception:
        pass
    status = getattr(exc, "status_code", None)
    return status in _RETRYABLE_STATUS


def _backoff(retries: int) -> float:
    # Exponential backoff with jitter, capped.
    return min(300.0, float(2**retries)) + random.uniform(0, 1)


@shared_task(bind=True, max_retries=5)
def send_outbound_email(self, email_id: str, subject: str, text: str, html: str | None = None):
    try:
        email = OutboundEmail.objects.get(id=email_id)
    except OutboundEmail.DoesNotExist:
        return

    # Idempotent: never send the same record twice.
    if email.status in (OutboundEmail.Status.SENT, OutboundEmail.Status.DELIVERED):
        return

    email.attempts += 1
    provider = get_email_provider()
    message = EmailMessageData(
        to=email.recipient,
        subject=subject,
        text=text,
        html=html,
        from_email=email.sender or None,
        headers={"X-Entity-Ref-ID": str(email.id)},
        idempotency_key=email.idempotency_key,
    )

    try:
        result = provider.send(message)
    except Exception as exc:
        email.last_error = f"{type(exc).__name__}: {exc}"[:500]
        if _is_retryable(exc) and self.request.retries < self.max_retries:
            email.status = OutboundEmail.Status.QUEUED
            email.save(update_fields=["attempts", "last_error", "status", "updated_at"])
            raise self.retry(exc=exc, countdown=_backoff(self.request.retries))
        email.status = OutboundEmail.Status.FAILED
        email.failed_at = timezone.now()
        email.save(
            update_fields=["attempts", "last_error", "status", "failed_at", "updated_at"]
        )
        return

    email.provider = result.provider
    email.provider_message_id = result.message_id or ""
    email.status = OutboundEmail.Status.SENT
    email.sent_at = timezone.now()
    email.last_error = ""
    email.save(
        update_fields=[
            "attempts",
            "provider",
            "provider_message_id",
            "status",
            "sent_at",
            "last_error",
            "updated_at",
        ]
    )
    record_event(
        AuditEvent.EventType.EMAIL_SUBMISSION,
        actor=email.user,
        target=("outbound_email", email.id),
        metadata={"email_type": email.email_type, "provider": result.provider},
    )

"""Resend (Svix) webhook verification and event processing.

Signatures are verified against the raw request body BEFORE any JSON is trusted.
Events are idempotent on ``svix_id`` and applied with a state-rank guard so
out-of-order deliveries never downgrade a later status.
"""
from django.conf import settings
from django.utils import timezone

from authsvc.apps.audit.models import AuditEvent
from authsvc.apps.audit.services import record_event

from .models import OutboundEmail, WebhookEvent

_EVENT_STATUS = {
    "email.sent": OutboundEmail.Status.SENT,
    "email.delivered": OutboundEmail.Status.DELIVERED,
    "email.delivery_delayed": None,
    "email.bounced": OutboundEmail.Status.BOUNCED,
    "email.complained": OutboundEmail.Status.COMPLAINED,
    "email.failed": OutboundEmail.Status.FAILED,
    "email.suppressed": OutboundEmail.Status.SUPPRESSED,
}

_STATUS_RANK = {
    OutboundEmail.Status.QUEUED: 0,
    OutboundEmail.Status.SENT: 1,
    OutboundEmail.Status.DELIVERED: 2,
    OutboundEmail.Status.FAILED: 2,
    OutboundEmail.Status.BOUNCED: 2,
    OutboundEmail.Status.SUPPRESSED: 2,
    OutboundEmail.Status.COMPLAINED: 3,
}


class WebhookError(Exception):
    """Signature verification or configuration failure."""


def verify_and_parse(raw_body: bytes, headers: dict) -> dict:
    """Verify the Svix signature over the raw body and return the parsed event.

    Raises WebhookError on a missing secret or an invalid/stale signature.
    """
    secret = getattr(settings, "RESEND_WEBHOOK_SECRET", "")
    if not secret:
        raise WebhookError("Webhook secret not configured")

    from svix.webhooks import Webhook, WebhookVerificationError

    svix_headers = {
        "svix-id": headers.get("svix-id", ""),
        "svix-timestamp": headers.get("svix-timestamp", ""),
        "svix-signature": headers.get("svix-signature", ""),
    }
    try:
        return Webhook(secret).verify(raw_body, svix_headers)
    except WebhookVerificationError as exc:
        raise WebhookError("Invalid signature") from exc


def process_event(svix_id: str, event: dict) -> WebhookEvent:
    """Idempotently record and apply a verified event."""
    event_type = event.get("type", "")
    data = event.get("data", {}) or {}
    message_id = data.get("email_id") or data.get("id") or ""

    webhook_event, created = WebhookEvent.objects.get_or_create(
        svix_id=svix_id,
        defaults=dict(
            event_type=event_type,
            provider_message_id=message_id,
            payload={"type": event_type, "email_id": message_id},  # sanitized: no PII/body
        ),
    )
    if not created and webhook_event.processed:
        return webhook_event  # duplicate delivery — no-op

    _apply_status(event_type, message_id)

    webhook_event.event_type = event_type
    webhook_event.provider_message_id = message_id
    webhook_event.processed = True
    webhook_event.processed_at = timezone.now()
    webhook_event.save()
    return webhook_event


def _apply_status(event_type: str, message_id: str) -> None:
    new_status = _EVENT_STATUS.get(event_type)
    if new_status is None or not message_id:
        return

    email = OutboundEmail.objects.filter(provider_message_id=message_id).first()
    if email is None:
        return

    # Out-of-order guard: never downgrade to a lower-ranked status.
    if _STATUS_RANK.get(new_status, 0) < _STATUS_RANK.get(email.status, 0):
        return

    email.status = new_status
    if new_status == OutboundEmail.Status.DELIVERED:
        email.delivered_at = timezone.now()
    elif new_status in (OutboundEmail.Status.FAILED, OutboundEmail.Status.BOUNCED):
        email.failed_at = timezone.now()
    email.save(update_fields=["status", "delivered_at", "failed_at", "updated_at"])
    audit_type = {
        OutboundEmail.Status.BOUNCED: AuditEvent.EventType.EMAIL_BOUNCE,
        OutboundEmail.Status.COMPLAINED: AuditEvent.EventType.EMAIL_COMPLAINT,
    }.get(new_status)
    if audit_type:
        record_event(
            audit_type,
            target=("outbound_email", email.id),
            metadata={"provider_message_id": message_id},
        )

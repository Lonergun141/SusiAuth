"""Email overhaul: provider, outbound records, on-commit dispatch, idempotency,
and Resend (Svix) webhook verification/processing."""
import base64
import datetime
import json

import pytest
from django.db import transaction

from authsvc.apps.notifications.models import OutboundEmail, WebhookEvent
from authsvc.apps.notifications.providers import InMemoryEmailProvider
from authsvc.apps.notifications.services import (
    send_password_reset_email,
    send_verification_email,
)

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"0123456789abcdef0123456789abcdef").decode()


@pytest.fixture(autouse=True)
def _clear_outbox():
    InMemoryEmailProvider.clear()
    yield
    InMemoryEmailProvider.clear()


# --- sending -----------------------------------------------------------------
def test_verification_email_rendered_and_sent(user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        send_verification_email(user, "654321", expiry_minutes=5)

    email = OutboundEmail.objects.get()
    assert email.email_type == "verification"
    assert email.status == OutboundEmail.Status.SENT
    assert email.provider == "inmemory"
    assert email.provider_message_id

    assert len(InMemoryEmailProvider.outbox) == 1
    msg = InMemoryEmailProvider.outbox[0]
    assert msg.subject == "Verify your email"
    assert msg.idempotency_key == email.idempotency_key
    assert "654321" in msg.text
    assert msg.html and "654321" in msg.html


def test_outbound_record_stores_no_secret(user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        send_password_reset_email(user, "https://app/reset?token=SECRETTOKEN", expiry_minutes=15)

    email = OutboundEmail.objects.get()
    # The raw token/link must never be persisted on the record.
    blob = json.dumps(
        {f: getattr(email, f) for f in ("subject", "template_name", "idempotency_key", "last_error")}
    )
    assert "SECRETTOKEN" not in blob


def test_dispatch_only_after_commit(user, django_capture_on_commit_callbacks):
    class Rollback(Exception):
        pass

    with django_capture_on_commit_callbacks(execute=True):
        try:
            with transaction.atomic():
                send_verification_email(user, "222222", expiry_minutes=5)
                raise Rollback
        except Rollback:
            pass

    # Rolled back: neither the record nor the send survive.
    assert OutboundEmail.objects.count() == 0
    assert InMemoryEmailProvider.outbox == []


def test_idempotent_no_duplicate_send(user, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        send_verification_email(user, "111111", expiry_minutes=5)
    with django_capture_on_commit_callbacks(execute=True):
        send_verification_email(user, "111111", expiry_minutes=5)

    assert OutboundEmail.objects.count() == 1
    assert len(InMemoryEmailProvider.outbox) == 1


# --- webhooks ----------------------------------------------------------------
def _signed(secret, msg_id, payload):
    from svix.webhooks import Webhook

    ts = datetime.datetime.now(tz=datetime.timezone.utc)
    sig = Webhook(secret).sign(msg_id, ts, payload)
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(ts.timestamp())),
        "svix-signature": sig,
    }


def _outbound(message_id="msg_abc", status=OutboundEmail.Status.SENT):
    return OutboundEmail.objects.create(
        email_type="verification",
        recipient="a@b.com",
        subject="x",
        idempotency_key=f"k/{message_id}",
        provider_message_id=message_id,
        status=status,
    )


def test_webhook_valid_signature_marks_delivered(client, settings):
    settings.RESEND_WEBHOOK_SECRET = WEBHOOK_SECRET
    email = _outbound("msg_abc")
    payload = json.dumps({"type": "email.delivered", "data": {"email_id": "msg_abc"}})
    headers = _signed(WEBHOOK_SECRET, "evt_1", payload)

    resp = client.post(
        "/api/v1/webhooks/resend", data=payload, content_type="application/json", headers=headers
    )

    assert resp.status_code == 200
    email.refresh_from_db()
    assert email.status == OutboundEmail.Status.DELIVERED
    assert email.delivered_at is not None
    assert WebhookEvent.objects.filter(svix_id="evt_1", processed=True).count() == 1


def test_webhook_invalid_signature_rejected(client, settings):
    settings.RESEND_WEBHOOK_SECRET = WEBHOOK_SECRET
    email = _outbound("msg_def")
    payload = json.dumps({"type": "email.delivered", "data": {"email_id": "msg_def"}})
    headers = _signed(WEBHOOK_SECRET, "evt_2", payload)
    headers["svix-signature"] = "v1,YmFkc2lnbmF0dXJl"  # tampered

    resp = client.post(
        "/api/v1/webhooks/resend", data=payload, content_type="application/json", headers=headers
    )

    assert resp.status_code == 400
    email.refresh_from_db()
    assert email.status == OutboundEmail.Status.SENT  # unchanged
    assert WebhookEvent.objects.count() == 0


def test_webhook_duplicate_delivery_is_idempotent(client, settings):
    from authsvc.apps.audit.models import AuditEvent

    settings.RESEND_WEBHOOK_SECRET = WEBHOOK_SECRET
    _outbound("msg_ghi")
    payload = json.dumps({"type": "email.bounced", "data": {"email_id": "msg_ghi"}})
    headers = _signed(WEBHOOK_SECRET, "evt_dup", payload)

    r1 = client.post("/api/v1/webhooks/resend", data=payload, content_type="application/json", headers=headers)
    r2 = client.post("/api/v1/webhooks/resend", data=payload, content_type="application/json", headers=headers)

    assert r1.status_code == 200 and r2.status_code == 200
    assert WebhookEvent.objects.filter(svix_id="evt_dup").count() == 1
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.EMAIL_BOUNCE
    ).count() == 1


def test_webhook_complaint_creates_security_event(client, settings):
    from authsvc.apps.audit.models import AuditEvent

    settings.RESEND_WEBHOOK_SECRET = WEBHOOK_SECRET
    _outbound("msg_complaint")
    payload = json.dumps(
        {"type": "email.complained", "data": {"email_id": "msg_complaint"}}
    )
    headers = _signed(WEBHOOK_SECRET, "evt_complaint", payload)

    response = client.post(
        "/api/v1/webhooks/resend",
        data=payload,
        content_type="application/json",
        headers=headers,
    )

    assert response.status_code == 200
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.EMAIL_COMPLAINT
    ).count() == 1


def test_webhook_out_of_order_does_not_downgrade(client, settings):
    settings.RESEND_WEBHOOK_SECRET = WEBHOOK_SECRET
    email = _outbound("msg_ooo", status=OutboundEmail.Status.DELIVERED)
    # A late "sent" event arrives after "delivered" — must not downgrade.
    payload = json.dumps({"type": "email.sent", "data": {"email_id": "msg_ooo"}})
    headers = _signed(WEBHOOK_SECRET, "evt_late", payload)

    resp = client.post(
        "/api/v1/webhooks/resend", data=payload, content_type="application/json", headers=headers
    )

    assert resp.status_code == 200
    email.refresh_from_db()
    assert email.status == OutboundEmail.Status.DELIVERED

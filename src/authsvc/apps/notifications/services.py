"""High-level email API used by the auth flows.

Renders templates where the secret is available, persists a secret-free
OutboundEmail record, and enqueues delivery on transaction commit. Callers use
the typed helpers; they never touch Celery or the provider directly.
"""
from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import transaction
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone

from .models import OutboundEmail
from .tasks import send_outbound_email


def _digest(*parts) -> str:
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def _base_context() -> dict:
    return {
        "product_name": "SusiAuth",
        "support_email": getattr(settings, "EMAIL_SUPPORT_ADDRESS", settings.DEFAULT_FROM_EMAIL),
    }


def _queue(*, email_type, to, subject, template_base, context, idempotency_key, user=None):
    """Render now, persist a secret-free record, enqueue on commit.

    Deduplicates on ``idempotency_key``: an email already sent/delivered is not
    re-sent; a queued/failed one is re-enqueued (retry reuses the same key).
    """
    text = render_to_string(f"{template_base}.txt", context)
    try:
        html = render_to_string(f"{template_base}.html", context)
    except TemplateDoesNotExist:
        html = None

    with transaction.atomic():
        email, created = OutboundEmail.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults=dict(
                email_type=email_type,
                recipient=to,
                subject=subject,
                template_name=template_base,
                user=user,
                sender=settings.DEFAULT_FROM_EMAIL,
                status=OutboundEmail.Status.QUEUED,
                queued_at=timezone.now(),
            ),
        )
        if not created and email.status in (
            OutboundEmail.Status.SENT,
            OutboundEmail.Status.DELIVERED,
        ):
            return email

        if not getattr(settings, "EMAIL_DELIVERY_ENABLED", True):
            return email

        eid = str(email.id)
        transaction.on_commit(lambda: send_outbound_email.delay(eid, subject, text, html))

    return email


def send_verification_email(user, code: str, *, expiry_minutes: int):
    context = _base_context() | {
        "first_name": user.first_name or "there",
        "code": code,
        "expiry_minutes": expiry_minutes,
    }
    return _queue(
        email_type="verification",
        to=user.email,
        subject="Verify your email",
        template_base="emails/verify_email",
        context=context,
        idempotency_key="verify-email/" + _digest(user.pk, code),
        user=user,
    )


def send_password_reset_email(user, reset_url: str, *, expiry_minutes: int):
    context = _base_context() | {
        "first_name": user.first_name or "there",
        "reset_url": reset_url,
        "expiry_minutes": expiry_minutes,
    }
    return _queue(
        email_type="password_reset",
        to=user.email,
        subject="Reset your password",
        template_base="emails/password_reset",
        context=context,
        idempotency_key="password-reset/" + _digest(reset_url),
        user=user,
    )


def send_password_changed_email(user):
    # Per-minute bucket: dedupes accidental double-calls, still notifies genuine
    # separate changes.
    minute_bucket = int(timezone.now().timestamp()) // 60
    context = _base_context() | {"first_name": user.first_name or "there"}
    return _queue(
        email_type="password_changed",
        to=user.email,
        subject="Your password was changed",
        template_base="emails/password_changed",
        context=context,
        idempotency_key="password-changed/" + _digest(user.pk, minute_bucket),
        user=user,
    )

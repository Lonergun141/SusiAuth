import uuid

from django.conf import settings
from django.db import models


class OutboundEmail(models.Model):
    """A record of one outbound authentication email.

    Deliberately stores NO sensitive content: no OTP codes, reset/verification
    tokens, links, or rendered bodies. Those are rendered where the secret
    exists (the web request) and passed to the Celery task transiently — only
    metadata, status, provider ids and the idempotency key are persisted.
    """

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"  # accepted by the provider
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        BOUNCED = "bounced", "Bounced"
        COMPLAINED = "complained", "Complained"
        SUPPRESSED = "suppressed", "Suppressed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email_type = models.CharField(max_length=64)
    recipient = models.EmailField()
    sender = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=255)
    template_name = models.CharField(max_length=128, blank=True, default="")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="emails",
    )
    idempotency_key = models.CharField(max_length=255, unique=True)

    provider = models.CharField(max_length=32, blank=True, default="")
    provider_message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["email_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.email_type} -> {self.recipient} ({self.status})"


class WebhookEvent(models.Model):
    """A received Resend (Svix) webhook event. Unique on svix_id for idempotency."""

    svix_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=64)
    provider_message_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    event_ts = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    processed_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.event_type} ({self.svix_id})"

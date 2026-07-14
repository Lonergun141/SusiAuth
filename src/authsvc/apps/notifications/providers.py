"""Email provider abstraction.

All Resend-specific behaviour is confined here (via Anymail's Resend backend).
The rest of the codebase talks to ``EmailProvider``, never the Resend SDK
directly. ``EMAIL_PROVIDER`` (settings) selects the concrete implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from django.conf import settings


@dataclass
class EmailMessageData:
    to: str
    subject: str
    text: str
    html: str | None = None
    from_email: str | None = None
    headers: dict = field(default_factory=dict)


@dataclass
class EmailSendResult:
    provider: str
    message_id: str | None = None


class EmailProvider(Protocol):
    name: str

    def send(self, message: EmailMessageData) -> EmailSendResult: ...


class DjangoMailProvider:
    """Sends through Django's configured EMAIL_BACKEND.

    Covers the console backend (dev) and Anymail's Resend backend (prod) — the
    concrete transport is chosen by ``EMAIL_BACKEND``. Captures the provider
    message id when the backend exposes one (Anymail sets ``anymail_status``).
    """

    name = "django"

    def send(self, message: EmailMessageData) -> EmailSendResult:
        from django.core.mail import EmailMultiAlternatives

        email = EmailMultiAlternatives(
            subject=message.subject,
            body=message.text,
            from_email=message.from_email or settings.DEFAULT_FROM_EMAIL,
            to=[message.to],
            headers=message.headers or None,
        )
        if message.html:
            email.attach_alternative(message.html, "text/html")
        email.send()

        message_id = None
        status = getattr(email, "anymail_status", None)
        if status is not None:
            message_id = getattr(status, "message_id", None)

        provider = "resend" if "resend" in settings.EMAIL_BACKEND else "console"
        return EmailSendResult(provider=provider, message_id=message_id)


class InMemoryEmailProvider:
    """Captures messages in memory for tests. Never touches the network."""

    name = "inmemory"
    outbox: list[EmailMessageData] = []

    @classmethod
    def clear(cls) -> None:
        cls.outbox = []

    def send(self, message: EmailMessageData) -> EmailSendResult:
        type(self).outbox.append(message)
        return EmailSendResult(provider="inmemory", message_id=f"inmemory-{len(self.outbox)}")


def get_email_provider() -> EmailProvider:
    if getattr(settings, "EMAIL_PROVIDER", "console") == "inmemory":
        return InMemoryEmailProvider()
    return DjangoMailProvider()

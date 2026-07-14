"""Resend backend extension for provider-level idempotency."""

from anymail.backends.resend import EmailBackend as AnymailResendBackend


class EmailBackend(AnymailResendBackend):
    """Put the delivery key on the Resend HTTP request, not the email body."""

    def build_message_payload(self, message, defaults):
        payload = super().build_message_payload(message, defaults)
        idempotency_key = getattr(message, "resend_idempotency_key", "")
        if idempotency_key:
            payload.headers["Idempotency-Key"] = idempotency_key
        return payload

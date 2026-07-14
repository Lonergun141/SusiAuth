from django.conf import settings
from django.db import models


class TOTPDevice(models.Model):
    """A user's TOTP authenticator. Secret is stored encrypted at rest.

    One device per user for now; structured so other factor types (WebAuthn)
    can be added as sibling models without reworking account authentication.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="totp_device"
    )
    secret_encrypted = models.TextField()
    confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"TOTP({self.user_id}, confirmed={self.confirmed})"


class RecoveryCode(models.Model):
    """A single-use MFA recovery code, stored only as a SHA-256 hash."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recovery_codes"
    )
    code_hash = models.CharField(max_length=64, db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "code_hash"])]

    def __str__(self) -> str:
        return f"RecoveryCode({self.user_id}, used={self.used_at is not None})"

from django.db import models
from django.conf import settings
from django.utils import timezone
from authsvc.apps.common.security import secure_random_token

class RefreshToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="refresh_tokens")
    token = models.CharField(max_length=255, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secure_random_token()
        if not self.expires_at:
            # Default to 30 days if not set, though service usually sets it
            self.expires_at = timezone.now() + timezone.timedelta(seconds=settings.JWT_REFRESH_TTL_SECONDS)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_revoked(self):
        return self.revoked_at is not None

class OneTimeToken(models.Model):
    PURPOSE_VERIFY_EMAIL = "verify_email"
    PURPOSE_RESET_PASSWORD = "reset_password"

    PURPOSE_CHOICES = (
        (PURPOSE_VERIFY_EMAIL, "Verify Email"),
        (PURPOSE_RESET_PASSWORD, "Reset Password"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="one_time_tokens")
    token = models.CharField(max_length=255, unique=True, db_index=True)
    purpose = models.CharField(max_length=50, choices=PURPOSE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secure_random_token()
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self):
        return self.consumed_at is not None

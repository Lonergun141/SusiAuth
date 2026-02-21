from django.db import models
from django.conf import settings
from django.utils import timezone
from authsvc.apps.common.security import secure_random_token, sha256_hex

class RefreshToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="refresh_tokens")
    session = models.ForeignKey("accounts.UserSession", on_delete=models.CASCADE, related_name="refresh_tokens", null=True, blank=True)
    token = models.CharField(max_length=255, unique=True, db_index=True)
    family_id = models.UUIDField(null=True, blank=True)
    replaced_by = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name="replaced_tokens")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not getattr(self, '_raw_token', None) and not self.pk:
            raw_token = secure_random_token()
            self._raw_token = raw_token
            self.token = sha256_hex(raw_token)
            if not self.family_id:
                import uuid
                self.family_id = uuid.uuid4()
            
        if not self.expires_at:
            # Default to 30 days if not set, though service usually sets it
            self.expires_at = timezone.now() + timezone.timedelta(seconds=settings.JWT_REFRESH_TTL_SECONDS)
        super().save(*args, **kwargs)

    @property
    def raw_token(self):
        return getattr(self, '_raw_token', None)

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
    attempts = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not getattr(self, '_raw_token', None) and not self.pk:
            raw_token = secure_random_token()
            self._raw_token = raw_token
            self.token = sha256_hex(raw_token)
        super().save(*args, **kwargs)

    @property
    def raw_token(self):
        return getattr(self, '_raw_token', None)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self):
        return self.consumed_at is not None

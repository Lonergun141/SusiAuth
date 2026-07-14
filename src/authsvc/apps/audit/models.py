"""Immutable security audit records."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Audit events are append-only and cannot be updated.")

    def delete(self):
        raise ValidationError("Audit events are append-only and cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Audit events are append-only and cannot be updated.")


class AuditEvent(models.Model):
    """A scalar snapshot of a security-relevant action.

    Actor and target identifiers deliberately are not foreign keys: deleting or
    changing a domain object must never mutate the historical audit record.
    """

    class EventType(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        VERIFICATION = "verification", "Verification"
        LOGIN_SUCCESS = "login_success", "Login success"
        LOGIN_FAILURE = "login_failure", "Login failure"
        REFRESH_SUCCESS = "refresh_success", "Refresh success"
        REFRESH_FAILURE = "refresh_failure", "Refresh failure"
        REFRESH_TOKEN_REUSE = "refresh_token_reuse", "Refresh-token reuse"
        LOGOUT = "logout", "Logout"
        LOGOUT_ALL = "logout_all", "Logout all"
        PASSWORD_CHANGE = "password_change", "Password change"
        PASSWORD_RESET = "password_reset", "Password reset"
        MFA_ENROLLMENT = "mfa_enrollment", "MFA enrollment"
        MFA_REMOVAL = "mfa_removal", "MFA removal"
        RECOVERY_CODE_USAGE = "recovery_code_usage", "Recovery-code usage"
        SESSION_REVOCATION = "session_revocation", "Session revocation"
        ACCOUNT_LOCK = "account_lock", "Account lock"
        ACCOUNT_SUSPENSION = "account_suspension", "Account suspension"
        ROLE_CHANGE = "role_change", "Role change"
        PERMISSION_CHANGE = "permission_change", "Permission change"
        OAUTH_CLIENT_CREATED = "oauth_client_created", "OAuth client created"
        OAUTH_CLIENT_UPDATED = "oauth_client_updated", "OAuth client updated"
        OAUTH_CLIENT_DELETED = "oauth_client_deleted", "OAuth client deleted"
        SIGNING_KEY_CHANGE = "signing_key_change", "Signing-key change"
        EMAIL_SUBMISSION = "email_submission", "Email submission"
        EMAIL_BOUNCE = "email_bounce", "Email bounce"
        EMAIL_COMPLAINT = "email_complaint", "Email complaint"
        ADMIN_ACTION = "admin_action", "Administrative action"

    class Result(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=64, choices=EventType.choices, db_index=True)
    result = models.CharField(max_length=16, choices=Result.choices, db_index=True)
    actor_type = models.CharField(max_length=32, default="anonymous")
    actor_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    target_type = models.CharField(max_length=64, blank=True, default="")
    target_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    request_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Audit events are append-only and cannot be updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are append-only and cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.event_type} ({self.result}) at {self.occurred_at}"

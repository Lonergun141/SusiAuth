"""Audit django-oauth-toolkit client lifecycle changes without modifying DOT."""

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from oauth2_provider.models import get_application_model

from .models import AuditEvent
from .services import record_event

Application = get_application_model()


def _safe_client_metadata(application) -> dict:
    return {
        "name": application.name,
        "client_type": application.client_type,
        "authorization_grant_type": application.authorization_grant_type,
    }


@receiver(post_save, sender=Application, dispatch_uid="audit_oauth_client_save")
def audit_oauth_client_save(sender, instance, created, **kwargs):
    event_type = (
        AuditEvent.EventType.OAUTH_CLIENT_CREATED
        if created
        else AuditEvent.EventType.OAUTH_CLIENT_UPDATED
    )
    record_event(
        event_type,
        actor=("system", "django-oauth-toolkit"),
        target=("oauth_client", instance.pk),
        metadata=_safe_client_metadata(instance),
    )


@receiver(pre_delete, sender=Application, dispatch_uid="audit_oauth_client_delete")
def audit_oauth_client_delete(sender, instance, **kwargs):
    record_event(
        AuditEvent.EventType.OAUTH_CLIENT_DELETED,
        actor=("system", "django-oauth-toolkit"),
        target=("oauth_client", instance.pk),
        metadata=_safe_client_metadata(instance),
    )

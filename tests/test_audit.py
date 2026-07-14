"""Append-only security audit events and current-flow integrations."""

import pytest
from django.core.exceptions import ValidationError

pytestmark = pytest.mark.django_db


def test_audit_event_is_append_only_and_sanitizes_secrets(user):
    from authsvc.apps.audit.models import AuditEvent
    from authsvc.apps.audit.services import record_event

    event = record_event(
        AuditEvent.EventType.LOGIN_FAILURE,
        result=AuditEvent.Result.FAILURE,
        actor=user,
        target=user,
        metadata={
            "reason": "bad_credentials",
            "password": "do-not-store",
            "nested": {"refresh_token": "also-secret"},
        },
    )

    assert event.actor_id == str(user.uuid)
    assert event.target_id == str(user.uuid)
    assert event.metadata["reason"] == "bad_credentials"
    assert event.metadata["password"] == "[REDACTED]"
    assert event.metadata["nested"]["refresh_token"] == "[REDACTED]"

    event.result = AuditEvent.Result.SUCCESS
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
    with pytest.raises(ValidationError):
        AuditEvent.objects.filter(pk=event.pk).update(result=AuditEvent.Result.SUCCESS)
    with pytest.raises(ValidationError):
        AuditEvent.objects.filter(pk=event.pk).delete()


def test_login_success_and_failure_are_audited(client, user):
    from authsvc.apps.audit.models import AuditEvent

    failed = client.post(
        "/api/v1/auth/login",
        data={"email": user.email, "password": "incorrect-password"},
        content_type="application/json",
        HTTP_X_REQUEST_ID="req-failed-login",
        HTTP_USER_AGENT="pytest-agent",
    )
    succeeded = client.post(
        "/api/v1/auth/login",
        data={"email": user.email, "password": "correct horse battery staple"},
        content_type="application/json",
        HTTP_X_REQUEST_ID="req-success-login",
    )

    assert failed.status_code == 401
    assert succeeded.status_code == 200
    failure_event = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.LOGIN_FAILURE
    )
    success_event = AuditEvent.objects.get(
        event_type=AuditEvent.EventType.LOGIN_SUCCESS
    )
    assert failure_event.request_id == "req-failed-login"
    assert failure_event.user_agent == "pytest-agent"
    assert failure_event.result == AuditEvent.Result.FAILURE
    assert success_event.target_id == str(user.uuid)


def test_oauth_client_lifecycle_is_audited(user):
    from oauth2_provider.models import get_application_model

    from authsvc.apps.audit.models import AuditEvent

    Application = get_application_model()
    application = Application.objects.create(
        name="audited-client",
        user=user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
        client_secret="never-audit-this",
    )
    application.name = "renamed-client"
    application.save(update_fields=["name"])
    target_id = str(application.pk)
    application.delete()

    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.OAUTH_CLIENT_CREATED,
        target_id=target_id,
    ).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.OAUTH_CLIENT_UPDATED,
        target_id=target_id,
    ).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.OAUTH_CLIENT_DELETED,
        target_id=target_id,
    ).exists()
    assert "never-audit-this" not in str(
        list(AuditEvent.objects.filter(target_id=target_id).values("metadata"))
    )


def test_registration_and_verification_are_audited(
    client, monkeypatch, django_capture_on_commit_callbacks
):
    import re

    from authsvc.api.v1.routers import auth as auth_router
    from authsvc.apps.audit.models import AuditEvent
    from authsvc.apps.notifications.providers import InMemoryEmailProvider

    monkeypatch.setattr(auth_router, "check_password_complexity", lambda password: None)
    InMemoryEmailProvider.clear()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            "/api/v1/auth/register",
            data={
                "email": "new-user@example.com",
                "password": "a sufficiently long password",
                "first_name": "New",
                "last_name": "User",
                "custom_fields": {},
            },
            content_type="application/json",
        )
    assert response.status_code == 201
    code = re.search(r"\b\d{6}\b", InMemoryEmailProvider.outbox[0].text).group()

    verified = client.post(
        "/api/v1/auth/verify-email",
        data={"email": "new-user@example.com", "code": code},
        content_type="application/json",
    )

    assert verified.status_code == 200
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.REGISTRATION,
        result=AuditEvent.Result.SUCCESS,
    ).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.VERIFICATION,
        result=AuditEvent.Result.SUCCESS,
    ).exists()


def test_session_and_password_lifecycle_is_audited(client, user, monkeypatch):
    from authsvc.api.v1.routers import auth as auth_router
    from authsvc.apps.audit.models import AuditEvent
    from authsvc.apps.tokens.models import OneTimeToken
    from authsvc.apps.tokens.services import create_one_time_token

    monkeypatch.setattr(auth_router, "check_password_complexity", lambda password: None)
    login = client.post(
        "/api/v1/auth/login",
        data={"email": user.email, "password": "correct horse battery staple"},
        content_type="application/json",
    ).json()
    refreshed = client.post(
        "/api/v1/auth/refresh",
        data={"refresh_token": login["refresh_token"]},
        content_type="application/json",
    )
    assert refreshed.status_code == 200
    logged_out = client.post(
        "/api/v1/auth/logout",
        data={"refresh_token": refreshed.json()["refresh_token"]},
        content_type="application/json",
    )
    assert logged_out.status_code == 200

    login = client.post(
        "/api/v1/auth/login",
        data={"email": user.email, "password": "correct horse battery staple"},
        content_type="application/json",
    ).json()
    auth_header = {"Authorization": f"Bearer {login['access_token']}"}
    changed = client.post(
        "/api/v1/auth/change-password",
        data={
            "current_password": "correct horse battery staple",
            "new_password": "a new sufficiently long password",
        },
        content_type="application/json",
        headers=auth_header,
    )
    assert changed.status_code == 200

    reset_token = create_one_time_token(
        user, OneTimeToken.PURPOSE_RESET_PASSWORD, ttl_minutes=15
    )
    reset = client.post(
        "/api/v1/auth/reset-password",
        data={
            "token": reset_token,
            "new_password": "another sufficiently long password",
        },
        content_type="application/json",
    )
    assert reset.status_code == 200

    for event_type in (
        AuditEvent.EventType.REFRESH_SUCCESS,
        AuditEvent.EventType.LOGOUT,
        AuditEvent.EventType.PASSWORD_CHANGE,
        AuditEvent.EventType.PASSWORD_RESET,
        AuditEvent.EventType.SESSION_REVOCATION,
    ):
        assert AuditEvent.objects.filter(event_type=event_type).exists()

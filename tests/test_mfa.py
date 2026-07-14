"""TOTP MFA: enrollment, verification, recovery codes, and the login challenge."""
import json

import pyotp
import pytest

from authsvc.apps.mfa import services
from authsvc.apps.mfa.models import RecoveryCode, TOTPDevice

PASSWORD = "correct horse battery staple"  # matches the `user` fixture


def _totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


# --- crypto / challenge token (no DB) ----------------------------------------
def test_secret_encrypted_roundtrip():
    from authsvc.apps.mfa.crypto import decrypt_secret, encrypt_secret

    secret = "JBSWY3DPEHPK3PXP"
    encrypted = encrypt_secret(secret)
    assert encrypted != secret
    assert decrypt_secret(encrypted) == secret


def test_mfa_challenge_token_roundtrip():
    import uuid

    from authsvc.apps.common.security import (
        make_access_jwt,
        make_mfa_challenge,
        verify_mfa_challenge,
    )

    sub = str(uuid.uuid4())
    payload = verify_mfa_challenge(make_mfa_challenge(sub))
    assert payload is not None
    assert payload["sub"] == sub and payload["purpose"] == "mfa"

    # A normal access token is NOT a valid MFA challenge.
    assert verify_mfa_challenge(make_access_jwt(sub, "a@b.com")) is None


# --- service layer -----------------------------------------------------------
@pytest.mark.django_db
def test_enrollment_confirm_enables_mfa(user):
    secret, uri = services.start_enrollment(user)
    assert uri.startswith("otpauth://")
    assert not user.mfa_enabled

    device = TOTPDevice.objects.get(user=user)
    assert device.confirmed is False
    assert device.secret_encrypted != secret  # stored encrypted, not raw

    codes = services.confirm_enrollment(user, _totp(secret))
    assert codes is not None and len(codes) == 10

    user.refresh_from_db()
    device.refresh_from_db()
    assert user.mfa_enabled
    assert device.confirmed
    assert RecoveryCode.objects.filter(user=user).count() == 10


@pytest.mark.django_db
def test_confirm_with_wrong_code_does_not_enable(user):
    services.start_enrollment(user)
    assert services.confirm_enrollment(user, "000000") is None
    user.refresh_from_db()
    assert not user.mfa_enabled


@pytest.mark.django_db
def test_verify_totp_and_recovery_single_use(user):
    secret, _ = services.start_enrollment(user)
    codes = services.confirm_enrollment(user, _totp(secret))

    assert services.verify_factor(user, _totp(secret)) == "totp"

    recovery = codes[0]
    assert services.verify_factor(user, recovery) == "recovery"
    assert services.verify_factor(user, recovery) is None  # already used
    assert services.remaining_recovery_codes(user) == 9


@pytest.mark.django_db
def test_disable_clears_everything(user):
    secret, _ = services.start_enrollment(user)
    services.confirm_enrollment(user, _totp(secret))

    services.disable(user)

    user.refresh_from_db()
    assert not user.mfa_enabled
    assert TOTPDevice.objects.filter(user=user).count() == 0
    assert RecoveryCode.objects.filter(user=user).count() == 0


# --- endpoints ---------------------------------------------------------------
def _login(client, email):
    return client.post(
        "/api/auth/login",
        data=json.dumps({"email": email, "password": PASSWORD}),
        content_type="application/json",
    ).json()


@pytest.mark.django_db
def test_login_without_mfa_returns_tokens(client, user):
    body = _login(client, user.email)
    assert body["mfa_required"] is False
    assert body["access_token"] and body["refresh_token"]


@pytest.mark.django_db
def test_login_with_mfa_returns_challenge_then_tokens(client, user):
    secret, _ = services.start_enrollment(user)
    services.confirm_enrollment(user, _totp(secret))

    body = _login(client, user.email)
    assert body["mfa_required"] is True
    assert body["mfa_token"]
    assert body["access_token"] is None  # no tokens until the 2nd factor

    resp = client.post(
        "/api/auth/mfa/verify",
        data=json.dumps({"mfa_token": body["mfa_token"], "code": _totp(secret)}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    tokens = resp.json()
    assert tokens["access_token"] and tokens["refresh_token"]


@pytest.mark.django_db
def test_mfa_verify_rejects_bad_code(client, user):
    secret, _ = services.start_enrollment(user)
    services.confirm_enrollment(user, _totp(secret))
    body = _login(client, user.email)

    resp = client.post(
        "/api/auth/mfa/verify",
        data=json.dumps({"mfa_token": body["mfa_token"], "code": "000000"}),
        content_type="application/json",
    )
    assert resp.status_code == 401


@pytest.mark.django_db
def test_setup_and_confirm_endpoints(client, user):
    from authsvc.apps.common.security import make_access_jwt

    headers = {"Authorization": f"Bearer {make_access_jwt(str(user.uuid), user.email)}"}

    r = client.post("/api/auth/mfa/setup", content_type="application/json", headers=headers)
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://")

    r2 = client.post(
        "/api/auth/mfa/confirm",
        data=json.dumps({"code": _totp(secret)}),
        content_type="application/json",
        headers=headers,
    )
    assert r2.status_code == 200
    assert len(r2.json()["recovery_codes"]) == 10
    user.refresh_from_db()
    assert user.mfa_enabled

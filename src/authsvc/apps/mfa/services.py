"""TOTP MFA business logic: enrollment, verification, recovery codes.

Routers stay thin and call into here. Verification tries TOTP first, then falls
back to single-use recovery codes.
"""
from __future__ import annotations

import hashlib
import secrets

import pyotp
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .crypto import decrypt_secret, encrypt_secret
from .models import RecoveryCode, TOTPDevice


def _hash_recovery(code: str) -> str:
    normalized = code.replace("-", "").replace(" ", "").lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def _generate_recovery_codes(user) -> list[str]:
    count = int(getattr(settings, "MFA_RECOVERY_CODE_COUNT", 10))
    RecoveryCode.objects.filter(user=user).delete()
    raw_codes = []
    to_create = []
    for _ in range(count):
        code = "-".join(secrets.token_hex(2) for _ in range(3))  # e.g. ab12-cd34-ef56
        raw_codes.append(code)
        to_create.append(RecoveryCode(user=user, code_hash=_hash_recovery(code)))
    RecoveryCode.objects.bulk_create(to_create)
    return raw_codes


def start_enrollment(user) -> tuple[str, str]:
    """Create (or reset) an unconfirmed TOTP device; return (secret, otpauth uri)."""
    secret = pyotp.random_base32()
    TOTPDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret_encrypted": encrypt_secret(secret),
            "confirmed": False,
            "confirmed_at": None,
            "last_used_at": None,
        },
    )
    issuer = getattr(settings, "MFA_ISSUER_NAME", "SusiAuth")
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=issuer)
    return secret, uri


def confirm_enrollment(user, code: str) -> list[str] | None:
    """Verify the first TOTP code, activate MFA, and return recovery codes once.

    Returns None if the code is invalid.
    """
    device = TOTPDevice.objects.filter(user=user).first()
    if device is None:
        return None

    secret = decrypt_secret(device.secret_encrypted)
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return None

    with transaction.atomic():
        device.confirmed = True
        device.confirmed_at = timezone.now()
        device.last_used_at = timezone.now()
        device.save(update_fields=["confirmed", "confirmed_at", "last_used_at"])
        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled", "updated_at"])
        codes = _generate_recovery_codes(user)
    return codes


def verify_factor(user, code: str) -> str | None:
    """Verify a login/reauth code. Returns "totp", "recovery", or None."""
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if device is None:
        return None

    secret = decrypt_secret(device.secret_encrypted)
    if pyotp.TOTP(secret).verify(code, valid_window=1):
        device.last_used_at = timezone.now()
        device.save(update_fields=["last_used_at"])
        return "totp"

    return "recovery" if _consume_recovery_code(user, code) else None


def _consume_recovery_code(user, code: str) -> bool:
    code_hash = _hash_recovery(code)
    with transaction.atomic():
        match = (
            RecoveryCode.objects.select_for_update()
            .filter(user=user, code_hash=code_hash, used_at__isnull=True)
            .first()
        )
        if match is None:
            return False
        match.used_at = timezone.now()
        match.save(update_fields=["used_at"])
    return True


def disable(user) -> None:
    with transaction.atomic():
        TOTPDevice.objects.filter(user=user).delete()
        RecoveryCode.objects.filter(user=user).delete()
        user.mfa_enabled = False
        user.save(update_fields=["mfa_enabled", "updated_at"])


def regenerate_recovery_codes(user) -> list[str]:
    return _generate_recovery_codes(user)


def remaining_recovery_codes(user) -> int:
    return RecoveryCode.objects.filter(user=user, used_at__isnull=True).count()

"""At-rest encryption for TOTP secrets.

Uses Fernet (from the already-present ``cryptography`` dependency) with a key
derived from ``MFA_SECRET_ENCRYPTION_KEY`` (falling back to ``SECRET_KEY``).
"""
import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    key_material = getattr(settings, "MFA_SECRET_ENCRYPTION_KEY", "") or settings.SECRET_KEY
    digest = hashlib.sha256(key_material.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()

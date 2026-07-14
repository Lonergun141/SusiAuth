"""Shared pytest fixtures for the auth service test suite."""
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture(scope="session", autouse=True)
def jwt_keys(tmp_path_factory):
    """Generate an ephemeral RSA keypair and point JWT settings at it.

    Keeps the suite self-contained — no committed or pre-generated keys, and no
    dependency on scripts/generate_keys.sh having been run.
    """
    from django.conf import settings

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_dir = tmp_path_factory.mktemp("jwt_keys")
    priv_path = key_dir / "jwt_private.pem"
    pub_path = key_dir / "jwt_public.pem"

    priv_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    settings.JWT_PRIVATE_KEY_PATH = str(priv_path)
    settings.JWT_PUBLIC_KEY_PATH = str(pub_path)
    yield


@pytest.fixture
def user(db):
    """An active, email-verified user."""
    from authsvc.apps.accounts.models import User

    return User.objects.create_user(
        email="alice@example.com",
        password="correct horse battery staple",
        is_active=True,
        is_email_verified=True,
    )

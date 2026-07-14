"""OAuth 2.1 / OIDC via django-oauth-toolkit.

Exercises the flows end-to-end with the Django test client (no browser needed):
client credentials, authorization code + PKCE, OIDC discovery/JWKS/UserInfo, and
rejection of the password (ROPC) grant.
"""
import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from django.urls import reverse
from oauth2_provider.models import get_application_model

Application = get_application_model()
PASSWORD = "correct horse battery staple"  # matches the `user` fixture
REDIRECT_URI = "https://client.example/callback"

pytestmark = pytest.mark.django_db


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _pkce_pair():
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def test_client_credentials_flow(client, user):
    app = Application.objects.create(
        name="service-client",
        user=user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
        client_secret="cc-raw-secret",
    )

    resp = client.post(
        reverse("oauth2_provider:token"),
        data={
            "grant_type": "client_credentials",
            "client_id": app.client_id,
            "client_secret": "cc-raw-secret",
            "scope": "read",
        },
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["token_type"].lower() == "bearer"
    assert body["access_token"]


def test_client_secret_is_hashed_at_rest(user):
    app = Application.objects.create(
        name="hashed-secret",
        user=user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS,
        client_secret="plain-secret",
    )
    app.refresh_from_db()
    assert app.client_secret != "plain-secret"  # stored hashed


def test_authorization_code_pkce_and_oidc(client, user):
    app = Application.objects.create(
        name="web-client",
        user=user,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=REDIRECT_URI,
        algorithm=Application.RS256_ALGORITHM,  # sign id_tokens with RS256
        skip_authorization=True,  # skip the consent page for the test
    )
    verifier, challenge = _pkce_pair()

    client.force_login(user)
    authorize = client.get(
        reverse("oauth2_provider:authorize"),
        data={
            "client_id": app.client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": "openid email profile",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "nonce": "n-123",
        },
    )
    assert authorize.status_code == 302, authorize.content
    code = parse_qs(urlparse(authorize["Location"]).query)["code"][0]

    token = client.post(
        reverse("oauth2_provider:token"),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": app.client_id,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200, token.content
    tok = token.json()
    assert tok["access_token"] and tok["refresh_token"]
    assert tok["id_token"]  # OIDC id_token because "openid" scope was requested

    # UserInfo with the access token returns our custom claims.
    userinfo = client.get(
        reverse("oauth2_provider:user-info"),
        HTTP_AUTHORIZATION=f"Bearer {tok['access_token']}",
    )
    assert userinfo.status_code == 200, userinfo.content
    claims = userinfo.json()
    assert claims["email"] == user.email


def test_authorization_code_requires_pkce(client, user):
    app = Application.objects.create(
        name="no-pkce",
        user=user,
        client_type=Application.CLIENT_PUBLIC,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=REDIRECT_URI,
        skip_authorization=True,
    )
    client.force_login(user)
    # No code_challenge -> rejected (PKCE_REQUIRED).
    resp = client.get(
        reverse("oauth2_provider:authorize"),
        data={
            "client_id": app.client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": "openid",
            "state": "xyz",
        },
    )
    # DOT redirects back with an error (or 400); either way, no auth code issued.
    if resp.status_code == 302:
        assert "code=" not in resp["Location"]
        assert "error=" in resp["Location"]
    else:
        assert resp.status_code == 400


def test_password_grant_is_rejected(client, user):
    app = Application.objects.create(
        name="ac-client",
        user=user,
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=REDIRECT_URI,
        client_secret="s3cret",
    )
    resp = client.post(
        reverse("oauth2_provider:token"),
        data={
            "grant_type": "password",
            "username": user.email,
            "password": PASSWORD,
            "client_id": app.client_id,
            "client_secret": "s3cret",
        },
    )
    assert resp.status_code in (400, 401)


def test_oidc_discovery_and_jwks(client):
    disc = client.get(reverse("oauth2_provider:oidc-connect-discovery-info"))
    assert disc.status_code == 200, disc.content
    meta = disc.json()
    for key in ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri", "userinfo_endpoint"):
        assert key in meta

    jwks = client.get(reverse("oauth2_provider:jwks-info"))
    assert jwks.status_code == 200
    assert jwks.json()["keys"]

"""Token & session lifecycle tests — the Phase 1 correctness fixes.

Covers the invariants recorded in CLAUDE.md:
  * login returns the RAW refresh token, never the stored hash
  * rotation continues the SAME session and mints exactly one replacement
  * reuse of a revoked token trips reuse detection and kills the family
  * concurrent rotation of one token lets exactly one caller win (Postgres)
"""
import threading

import pytest
from django.db import connection

from authsvc.apps.accounts.models import UserSession
from authsvc.apps.common.security import jwt_verify_rs256, sha256_hex
from authsvc.apps.tokens.models import RefreshToken
from authsvc.apps.tokens.services import (
    issue_token_pair,
    revoke_all_refresh_tokens,
    rotate_refresh_token,
)

pytestmark = pytest.mark.django_db


def test_issue_returns_raw_token_not_hash(user):
    access, raw_refresh = issue_token_pair(user, request=None)

    stored = RefreshToken.objects.get()
    # The DB holds only the hash; the raw token must not equal it.
    assert raw_refresh != stored.token
    assert sha256_hex(raw_refresh) == stored.token
    # Exactly one session, one token for a fresh login.
    assert UserSession.objects.count() == 1
    assert RefreshToken.objects.count() == 1


def test_access_token_verifies_and_carries_session(user):
    access, _ = issue_token_pair(user, request=None)

    payload = jwt_verify_rs256(access)
    assert payload["sub"] == str(user.uuid)
    assert payload["sid"]  # session id claim present
    session = UserSession.objects.get()
    assert payload["sid"] == str(session.session_id)


def test_rotation_keeps_same_session_and_single_replacement(user):
    _, raw1 = issue_token_pair(user, request=None)
    original = RefreshToken.objects.get()

    ret_user, access, raw2 = rotate_refresh_token(raw1, request=None)

    assert ret_user == user
    # No phantom session — still exactly one.
    assert UserSession.objects.count() == 1
    # Old + new = two tokens, in the same family and session.
    assert RefreshToken.objects.count() == 2
    new = RefreshToken.objects.get(revoked_at__isnull=True)
    assert new.family_id == original.family_id
    assert new.session_id == original.session_id
    assert raw2 != raw1

    original.refresh_from_db()
    assert original.is_revoked
    assert original.replaced_by_id == new.id

    # Access token is valid and bound to the continuing session.
    # NB: RefreshToken.session_id is the FK integer; the sid claim uses the
    # UserSession.session_id UUID.
    payload = jwt_verify_rs256(access)
    assert payload["sid"] == str(original.session.session_id)


def test_reuse_of_revoked_token_revokes_family(user):
    from authsvc.apps.audit.models import AuditEvent

    _, raw1 = issue_token_pair(user, request=None)
    _, _, raw2 = rotate_refresh_token(raw1, request=None)  # raw1 now revoked

    # Presenting the already-rotated token again = reuse.
    with pytest.raises(ValueError, match="reuse"):
        rotate_refresh_token(raw1, request=None)

    # The whole family/session is now dead — even the freshly issued raw2.
    session = UserSession.objects.get()
    assert session.is_active is False
    assert RefreshToken.objects.filter(revoked_at__isnull=True).count() == 0
    with pytest.raises(ValueError):
        rotate_refresh_token(raw2, request=None)
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.REFRESH_TOKEN_REUSE
    ).exists()
    assert AuditEvent.objects.filter(
        event_type=AuditEvent.EventType.SESSION_REVOCATION
    ).exists()


def test_unknown_token_raises(user):
    with pytest.raises(ValueError, match="not found"):
        rotate_refresh_token("nonexistent-token", request=None)


def test_expired_token_rejected(user):
    from datetime import timedelta

    from django.utils import timezone

    session = UserSession.objects.create(user=user)
    rt = RefreshToken(
        user=user,
        session=session,
        expires_at=timezone.now() - timedelta(days=1),
    )
    rt.save()
    raw = rt.raw_token

    with pytest.raises(ValueError, match="expired"):
        rotate_refresh_token(raw, request=None)


def test_revoke_all_deactivates_sessions_and_refresh_tokens(user):
    issue_token_pair(user, request=None)
    issue_token_pair(user, request=None)

    revoke_all_refresh_tokens(user)

    assert UserSession.objects.filter(user=user, is_active=True).count() == 0
    assert RefreshToken.objects.filter(user=user, revoked_at__isnull=True).count() == 0


@pytest.mark.django_db(transaction=True)
def test_concurrent_rotation_only_one_wins(user):
    """Two simultaneous rotations of the same token: exactly one succeeds.

    Requires real row locking, so it only runs on PostgreSQL. On SQLite
    ``select_for_update`` is a no-op and cross-thread in-memory connections
    don't share state, so we skip rather than assert something false.
    """
    if connection.vendor != "postgresql":
        pytest.skip("concurrency test requires PostgreSQL (select_for_update)")

    _, raw = issue_token_pair(user, request=None)

    results = {}
    barrier = threading.Barrier(2)

    def worker(name):
        barrier.wait()
        try:
            rotate_refresh_token(raw, request=None)
            results[name] = "ok"
        except ValueError:
            results[name] = "rejected"
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(n,)) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(results.values()) == ["ok", "rejected"]

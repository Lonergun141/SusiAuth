from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from ninja.errors import HttpError

from authsvc.apps.accounts.models import UserSession
from authsvc.apps.common.security import make_access_jwt, sha256_hex
from authsvc.apps.tokens.models import OneTimeToken, RefreshToken


def _client_meta(request):
    """Extract (ip_address, user_agent) from a request, tolerating None."""
    if not request:
        return None, None
    return request.META.get("REMOTE_ADDR"), request.META.get("HTTP_USER_AGENT")

def issue_token_pair(user, request) -> tuple[str, str]:
    """Create a brand-new session with an access token + refresh token.

    Used at login / email-verification (a fresh authentication). Returns the
    *raw* refresh token, which is the only time it is ever available — the DB
    only stores its SHA-256 hash.
    """
    ip_address, user_agent = _client_meta(request)

    # Create Session
    session = UserSession.objects.create(
        user=user,
        ip_address=ip_address,
        user_agent=user_agent
    )

    # 1. Create access token
    access = make_access_jwt(
        user_uuid=str(user.uuid),
        email=user.email,
        roles=["user"] if user.is_active else [],
        session_id=str(session.session_id)
    )

    # 2. Create refresh token
    refresh_ttl = getattr(settings, "JWT_REFRESH_TTL_SECONDS", 2592000)
    expires_at = timezone.now() + timedelta(seconds=refresh_ttl)

    refresh_obj = RefreshToken.objects.create(
        user=user,
        session=session,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent
    )

    return access, refresh_obj.raw_token

def _revoke_family(refresh_obj) -> None:
    """Reuse detection: kill the whole session/family the token belongs to."""
    session = refresh_obj.session
    if session:
        session.is_active = False
        session.save(update_fields=["is_active"])
        session.refresh_tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
    elif refresh_obj.family_id:
        RefreshToken.objects.filter(
            family_id=refresh_obj.family_id, revoked_at__isnull=True
        ).update(revoked_at=timezone.now())
    else:
        revoke_all_refresh_tokens(refresh_obj.user)


def rotate_refresh_token(token_str: str, request) -> tuple[object, str, str]:
    """Atomically rotate a refresh token within its existing session.

    Concurrency-safe: the matching row is locked with ``select_for_update`` so
    two simultaneous rotations of the same token cannot both succeed — the
    loser sees the (now-revoked) token and triggers reuse detection.

    Returns ``(user, access_token, new_raw_refresh_token)``.
    """
    token_hash = sha256_hex(token_str)
    refresh_ttl = getattr(settings, "JWT_REFRESH_TTL_SECONDS", 2592000)

    with transaction.atomic():
        try:
            refresh_obj = RefreshToken.objects.select_for_update().get(token=token_hash)
        except RefreshToken.DoesNotExist:
            raise ValueError("Token not found")

        if refresh_obj.is_revoked:
            # A revoked token is being presented again -> reuse detected. Revoke
            # the family here (committed on block exit); the ValueError is raised
            # *after* the transaction so the revocation is not rolled back.
            _revoke_family(refresh_obj)
            reused = True
        else:
            reused = False
            if refresh_obj.is_expired:
                raise ValueError("Token expired")

            session = refresh_obj.session
            if session and not session.is_active:
                raise ValueError("Session inactive")

            # Revoke the presented token.
            refresh_obj.revoked_at = timezone.now()
            refresh_obj.save(update_fields=["revoked_at"])

            user = refresh_obj.user
            ip_address, user_agent = _client_meta(request)

            if not session:
                session = UserSession.objects.create(
                    user=user, ip_address=ip_address, user_agent=user_agent
                )

            # One replacement refresh token, same family + session.
            new_refresh = RefreshToken.objects.create(
                user=user,
                session=session,
                family_id=refresh_obj.family_id,
                expires_at=timezone.now() + timedelta(seconds=refresh_ttl),
                ip_address=ip_address,
                user_agent=user_agent,
            )
            refresh_obj.replaced_by = new_refresh
            refresh_obj.save(update_fields=["replaced_by"])

            # One access token, bound to the continuing session.
            access = make_access_jwt(
                user_uuid=str(user.uuid),
                email=user.email,
                roles=["user"] if user.is_active else [],
                session_id=str(session.session_id),
            )

    if reused:
        raise ValueError("Token revoked (reuse detected)")

    return user, access, new_refresh.raw_token

def revoke_refresh_token(token_str: str):
    from authsvc.apps.common.security import sha256_hex
    try:
        refresh_obj = RefreshToken.objects.get(token=sha256_hex(token_str))
        refresh_obj.revoked_at = timezone.now()
        refresh_obj.save()
        
        if refresh_obj.session:
            refresh_obj.session.is_active = False
            refresh_obj.session.save()
    except RefreshToken.DoesNotExist:
        pass

def revoke_all_refresh_tokens(user):
    user.refresh_tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())

def create_one_time_token(user, purpose: str, ttl_minutes: int = 30) -> str:
    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
    ott = OneTimeToken.objects.create(
        user=user,
        purpose=purpose,
        expires_at=expires_at
    )
    return ott.raw_token

def consume_one_time_token(token_str: str, purpose: str):
    from authsvc.apps.common.security import sha256_hex
    try:
        ott = OneTimeToken.objects.get(token=sha256_hex(token_str), purpose=purpose)
    except OneTimeToken.DoesNotExist:
        raise HttpError(400, "Invalid or expired token")

    if ott.is_consumed:
        raise HttpError(400, "Token already used")
    
    if ott.is_expired:
        raise HttpError(400, "Token expired")

    ott.consumed_at = timezone.now()
    ott.save()
    return ott.user

def send_reset_password_email(user, token: str, *, expiry_minutes: int):
    # Lazy import avoids a heavy import chain at module load.
    from authsvc.apps.notifications import services as email_services

    link = settings.FRONTEND_RESET_PASSWORD_URL.format(token=token)
    email_services.send_password_reset_email(user, link, expiry_minutes=expiry_minutes)

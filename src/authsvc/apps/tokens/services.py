from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from ninja.errors import HttpError
from authsvc.apps.common.security import make_access_jwt
from authsvc.apps.common.emailer import send_auth_email
from authsvc.apps.tokens.models import RefreshToken, OneTimeToken

from authsvc.apps.accounts.models import UserSession

def issue_token_pair(user, request) -> tuple[str, str]:
    # Extract Device Info
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT")

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
    
    return access, refresh_obj.token

def rotate_refresh_token(token_str: str, request) -> tuple[any, str]:
    from authsvc.apps.common.security import sha256_hex
    try:
        refresh_obj = RefreshToken.objects.get(token=sha256_hex(token_str))
    except RefreshToken.DoesNotExist:
        raise ValueError("Token not found")

    if refresh_obj.is_revoked:
        # Security: Revoke all tokens for this user/session if a revoked token is reused (Reuse Detection)
        if refresh_obj.session:
            refresh_obj.session.is_active = False
            refresh_obj.session.save()
            refresh_obj.session.refresh_tokens.update(revoked_at=timezone.now())
        else:
            revoke_all_refresh_tokens(refresh_obj.user)
        raise ValueError("Token revoked (reuse detected)")

    if refresh_obj.is_expired:
        raise ValueError("Token expired")

    # Revoke current
    refresh_obj.revoked_at = timezone.now()
    refresh_obj.save(update_fields=["revoked_at"])

    # Issue new pair for the SAME session
    user = refresh_obj.user
    
    # Extract Device Info
    ip_address = None
    user_agent = None
    if request:
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT")
        
    session = refresh_obj.session
    if not session:
        session = UserSession.objects.create(user=user, ip_address=ip_address, user_agent=user_agent)

    access = make_access_jwt(
        user_uuid=str(user.uuid), 
        email=user.email, 
        roles=["user"] if user.is_active else [],
        session_id=str(session.session_id)
    )

    refresh_ttl = getattr(settings, "JWT_REFRESH_TTL_SECONDS", 2592000)
    new_refresh = RefreshToken.objects.create(
        user=user,
        session=session,
        family_id=refresh_obj.family_id,
        expires_at=timezone.now() + timedelta(seconds=refresh_ttl),
        ip_address=ip_address,
        user_agent=user_agent
    )
    
    refresh_obj.replaced_by = new_refresh
    refresh_obj.save(update_fields=["replaced_by"])

    return user, new_refresh.raw_token

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

def send_verify_email(user, token: str):
    link = settings.FRONTEND_VERIFY_EMAIL_URL.format(token=token)
    body = f"Please verify your email here: {link}"
    send_auth_email(user.email, "Verify your email", body)

def send_reset_password_email(user, token: str):
    link = settings.FRONTEND_RESET_PASSWORD_URL.format(token=token)
    body = f"Reset your password here: {link}"
    send_auth_email(user.email, "Reset Password", body)

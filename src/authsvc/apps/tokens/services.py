from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from ninja.errors import HttpError
from authsvc.apps.common.security import make_access_jwt
from authsvc.apps.tokens.models import RefreshToken, OneTimeToken

def issue_token_pair(user, request) -> tuple[str, str]:
    # 1. Create access token
    access = make_access_jwt(user.id, user.email, roles=["user"] if user.is_active else [])
    
    # 2. Create refresh token
    refresh_ttl = getattr(settings, "JWT_REFRESH_TTL_SECONDS", 2592000)
    expires_at = timezone.now() + timedelta(seconds=refresh_ttl)
    
    refresh_obj = RefreshToken.objects.create(
        user=user,
        expires_at=expires_at
    )
    
    return access, refresh_obj.token

def rotate_refresh_token(token_str: str, request) -> tuple[any, str]:
    try:
        refresh_obj = RefreshToken.objects.get(token=token_str)
    except RefreshToken.DoesNotExist:
        raise ValueError("Token not found")

    if refresh_obj.is_revoked:
        # Security: Revoke all tokens for this user if a revoked token is reused (Reuse Detection)
        revoke_all_refresh_tokens(refresh_obj.user)
        raise ValueError("Token revoked")

    if refresh_obj.is_expired:
        raise ValueError("Token expired")

    # Revoke current
    refresh_obj.revoked_at = timezone.now()
    refresh_obj.save()

    # Issue new pair
    user = refresh_obj.user
    _, new_refresh_token = issue_token_pair(user, request)
    return user, new_refresh_token

def revoke_refresh_token(token_str: str):
    try:
        refresh_obj = RefreshToken.objects.get(token=token_str)
        refresh_obj.revoked_at = timezone.now()
        refresh_obj.save()
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
    return ott.token

def consume_one_time_token(token_str: str, purpose: str):
    try:
        ott = OneTimeToken.objects.get(token=token_str, purpose=purpose)
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
    print(f"EMAIL [Verify]: To {user.email}, Link: {link}")
    # In real impl, use send_mail

def send_reset_password_email(user, token: str):
    link = settings.FRONTEND_RESET_PASSWORD_URL.format(token=token)
    print(f"EMAIL [Reset]: To {user.email}, Link: {link}")

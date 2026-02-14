from django.utils import timezone
from django.db import transaction
from ninja import Router
from ninja.errors import HttpError

from authsvc.api.v1.schemas import (
    RegisterIn, LoginIn, TokenOut, RefreshIn, LogoutIn,
    VerifyEmailIn, EmailIn, ResetPasswordIn, ChangePasswordIn, MeOut
)
from authsvc.api.v1.auth import auth
from authsvc.apps.accounts.models import User
from authsvc.apps.tokens.services import (
    issue_token_pair,
    rotate_refresh_token,
    revoke_refresh_token,
    revoke_all_refresh_tokens,
    create_one_time_token,
    consume_one_time_token,
    send_verify_email,
    send_reset_password_email,
)
from authsvc.apps.tokens.models import OneTimeToken

router = Router(tags=["auth"])


@router.post("/register", response={201: dict})
def register(request, data: RegisterIn):
    if User.objects.filter(email__iexact=data.email).exists():
        raise HttpError(400, "Email already registered")

    user = User.objects.create_user(
        email=data.email,
        password=data.password,
        first_name=data.first_name or "",
        last_name=data.last_name or "",
        is_active=True,
        is_email_verified=False,
    )

    token = create_one_time_token(user, OneTimeToken.PURPOSE_VERIFY_EMAIL, ttl_minutes=30)
    send_verify_email(user, token)
    return 201, {"message": "Registered. Please verify your email."}


@router.post("/verify-email", response={200: dict})
def verify_email(request, data: VerifyEmailIn):
    user = consume_one_time_token(data.token, OneTimeToken.PURPOSE_VERIFY_EMAIL)
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    return {"message": "Email verified"}


@router.post("/resend-verification", response={200: dict})
def resend_verification(request, data: EmailIn):
    user = User.objects.filter(email__iexact=data.email).first()
    if not user or user.is_email_verified:
        return {"message": "If the account exists, we sent an email."}

    token = create_one_time_token(user, OneTimeToken.PURPOSE_VERIFY_EMAIL, ttl_minutes=30)
    send_verify_email(user, token)
    return {"message": "If the account exists, we sent an email."}


@router.post("/login", response={200: TokenOut})
def login(request, data: LoginIn):
    user = User.objects.filter(email__iexact=data.email).first()
    if not user or not user.is_active or not user.check_password(data.password):
        raise HttpError(401, "Invalid credentials")

    access, refresh = issue_token_pair(user, request)
    return {"access_token": access, "refresh_token": refresh}


@router.post("/refresh", response={200: TokenOut})
def refresh(request, data: RefreshIn):
    try:
        user, new_refresh = rotate_refresh_token(data.refresh_token, request)
    except ValueError as e:
        raise HttpError(401, "Invalid refresh token") from e

    access, _ = issue_token_pair(user, request)
    # issue_token_pair issues a new refresh; we want the rotated one from the service:
    return {"access_token": access, "refresh_token": new_refresh}


@router.post("/logout", response={200: dict})
def logout(request, data: LogoutIn):
    revoke_refresh_token(data.refresh_token)
    return {"message": "Logged out"}


@router.post("/logout-all", response={200: dict}, auth=auth)
def logout_all(request):
    user_id = int(request.jwt["sub"])
    user = User.objects.get(id=user_id)
    revoke_all_refresh_tokens(user)
    return {"message": "Logged out of all sessions"}


@router.get("/me", response=MeOut, auth=auth)
def me(request):
    user_id = int(request.jwt["sub"])
    user = User.objects.get(id=user_id)
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_email_verified": user.is_email_verified,
    }


@router.post("/change-password", response={200: dict}, auth=auth)
def change_password(request, data: ChangePasswordIn):
    user_id = int(request.jwt["sub"])
    user = User.objects.get(id=user_id)
    if not user.check_password(data.current_password):
        raise HttpError(400, "Current password incorrect")

    user.set_password(data.new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_refresh_tokens(user)
    return {"message": "Password changed"}


@router.post("/forgot-password", response={200: dict})
def forgot_password(request, data: EmailIn):
    user = User.objects.filter(email__iexact=data.email, is_active=True).first()
    if not user:
        return {"message": "If the account exists, we sent an email."}

    token = create_one_time_token(user, OneTimeToken.PURPOSE_RESET_PASSWORD, ttl_minutes=30)
    send_reset_password_email(user, token)
    return {"message": "If the account exists, we sent an email."}


@router.post("/reset-password", response={200: dict})
@transaction.atomic
def reset_password(request, data: ResetPasswordIn):
    user = consume_one_time_token(data.token, OneTimeToken.PURPOSE_RESET_PASSWORD)
    if not user.is_active:
        raise HttpError(400, "User inactive")

    user.set_password(data.new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_refresh_tokens(user)
    return {"message": "Password reset successful"}

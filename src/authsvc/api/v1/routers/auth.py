from django.utils import timezone
from django.db import transaction
from django.conf import settings
from ninja import Router
from ninja.errors import HttpError

from authsvc.apps.accounts.models import User, RegistrationField, EmailOTP
from authsvc.apps.accounts.utils import generate_otp_code
from authsvc.apps.common.emailer import send_auth_email
from authsvc.apps.common.pwned import check_password_complexity
from authsvc.apps.tokens.services import (
    issue_token_pair,
    rotate_refresh_token,
    revoke_refresh_token,
    revoke_all_refresh_tokens,
    create_one_time_token,
    consume_one_time_token,
    send_reset_password_email,
)
from authsvc.apps.tokens.models import OneTimeToken
from authsvc.api.v1.auth import auth
from django_ratelimit.decorators import ratelimit
from authsvc.api.v1.schemas import (
    RegistrationFieldOut,
    RegisterIn,
    VerifyEmailIn,
    TokenOut,
    ResendVerificationIn,
    LoginIn,
    RefreshIn,
    LogoutIn,
    MeOut,
    ChangePasswordIn,
    EmailIn,
    ResetPasswordIn,
)

router = Router(tags=["auth"])


@router.get("/registration-fields", response=list[RegistrationFieldOut])
def get_registration_fields(request):
    return RegistrationField.objects.filter(is_active=True)


@router.post("/register", response={201: dict})
@ratelimit(key="ip", rate="3/m", block=True)
def register(request, data: RegisterIn):
    if User.objects.filter(email__iexact=data.email).exists():
        raise HttpError(400, "Email already registered")

    check_password_complexity(data.password)

    # Validate custom fields
    active_fields = RegistrationField.objects.filter(is_active=True)
    custom_data = {}
    
    for field in active_fields:
        value = data.custom_fields.get(field.name)
        if field.required and value is None:
             raise HttpError(400, f"Missing required field: {field.label}")
        
        # Basic type validation could go here
        if value is not None:
             custom_data[field.name] = value

    with transaction.atomic():
        user = User.objects.create_user(
            email=data.email,
            password=data.password,
            first_name=data.first_name or "",
            last_name=data.last_name or "",
            is_active=False,  # Inactive until verified
            is_email_verified=False,
            custom_fields=custom_data
        )

        from authsvc.apps.common.security import sha256_hex
        otp_ttl = int(getattr(settings, "OTP_TTL_MINUTES", 5))
        otp_code = generate_otp_code()
        expiry = timezone.now() + timezone.timedelta(minutes=otp_ttl)
        EmailOTP.objects.create(user=user, code_hash=sha256_hex(otp_code), expires_at=expiry)
    
    # Send Email
    send_auth_email(
        user.email,
        "Verify your email",
        f"Your verification code is: {otp_code}"
    )

    return 201, {"message": "Registered. Please check your email for the verification code."}


@router.post("/verify-email", response={200: TokenOut})
@ratelimit(key="ip", rate="5/m", block=True)
def verify_email(request, data: VerifyEmailIn):
    try:
        user = User.objects.get(email__iexact=data.email)
    except User.DoesNotExist:
        raise HttpError(400, "Invalid email or code")

    from authsvc.apps.common.security import sha256_hex
    
    # First, find any valid OTP for the user, order by newest.
    # In a high-security setup, we only let them attempt the LATEST OTP.
    otp = user.otps.filter(
        is_verified=False,
        expires_at__gt=timezone.now()
    ).order_by('-created_at').first()

    if not otp:
        raise HttpError(400, "Invalid or expired code")
    
    if otp.attempts >= 3:
         raise HttpError(400, "Too many failed attempts. Request a new code.")
         
    # Check Code
    if otp.code_hash != sha256_hex(data.code):
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        raise HttpError(400, "Invalid code")

    # Mark verified
    otp.is_verified = True
    otp.save()

    # Activate user
    user.is_email_verified = True
    user.is_active = True
    user.save(update_fields=["is_email_verified", "is_active"])
    
    # Clear other OTPs? Optional.

    access, refresh = issue_token_pair(user, request)
    return {"access_token": access, "refresh_token": refresh}


@router.post("/resend-verification", response={200: dict})
@ratelimit(key="ip", rate="3/m", block=True)
def resend_verification(request, data: ResendVerificationIn):
    user = User.objects.filter(email__iexact=data.email).first()
    if not user:
        # Security: don't reveal user existence
        return {"message": "If the account exists, we sent a code."}

    if user.is_email_verified:
         return {"message": "Account already verified."}

    # Cooldown Check
    last_otp = EmailOTP.objects.filter(user=user).order_by('-created_at').first()
    if last_otp and last_otp.created_at > timezone.now() - timezone.timedelta(minutes=1):
        raise HttpError(400, "Please wait before requesting another code.")

    from authsvc.apps.common.security import sha256_hex
    otp_ttl = int(getattr(settings, "OTP_TTL_MINUTES", 5))
    otp_code = generate_otp_code()
    expiry = timezone.now() + timezone.timedelta(minutes=otp_ttl)
    EmailOTP.objects.create(user=user, code_hash=sha256_hex(otp_code), expires_at=expiry)

    send_auth_email(
        user.email,
        "Verify your email",
        f"Your verification code is: {otp_code}"
    )
    
    return {"message": "If the account exists, we sent a code."}


@router.post("/login", response={200: TokenOut})
@ratelimit(key="ip", rate="5/15m", block=True)
def login(request, data: LoginIn):
    user = User.objects.filter(email__iexact=data.email).first()
    
    if user and user.check_password(data.password):
        if not user.is_email_verified:
            raise HttpError(401, "Email is not verified. Please verify your email address.")
        
        if not user.is_active:
             raise HttpError(401, "Account is disabled.")

        access, refresh = issue_token_pair(user, request)
        return {"access_token": access, "refresh_token": refresh}
    
    raise HttpError(401, "Invalid credentials")


@router.post("/refresh", response={200: TokenOut})
@ratelimit(key="ip", rate="20/m", block=True)
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
    user_uuid = request.jwt["sub"]
    user = User.objects.get(uuid=user_uuid)
    revoke_all_refresh_tokens(user)
    return {"message": "Logged out of all sessions"}


@router.get("/me", response=MeOut, auth=auth)
def me(request):
    user_uuid = request.jwt["sub"]
    user = User.objects.get(uuid=user_uuid)
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_email_verified": user.is_email_verified,
    }


@router.post("/change-password", response={200: dict}, auth=auth)
def change_password(request, data: ChangePasswordIn):
    user_uuid = request.jwt["sub"]
    user = User.objects.get(uuid=user_uuid)
    if not user.check_password(data.current_password):
        raise HttpError(400, "Current password incorrect")

    check_password_complexity(data.new_password)

    user.set_password(data.new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_refresh_tokens(user)
    return {"message": "Password changed"}


@router.post("/forgot-password", response={200: dict})
@ratelimit(key="ip", rate="3/m", block=True)
def forgot_password(request, data: EmailIn):
    user = User.objects.filter(email__iexact=data.email, is_active=True).first()
    if not user:
        return {"message": "If the account exists, we sent an email."}

    token = create_one_time_token(user, OneTimeToken.PURPOSE_RESET_PASSWORD, ttl_minutes=30)
    send_reset_password_email(user, token)
    return {"message": "If the account exists, we sent an email."}


@router.post("/reset-password", response={200: dict})
@ratelimit(key="ip", rate="3/m", block=True)
@transaction.atomic
def reset_password(request, data: ResetPasswordIn):
    user = consume_one_time_token(data.token, OneTimeToken.PURPOSE_RESET_PASSWORD)
    if not user.is_active:
        raise HttpError(400, "User inactive")

    check_password_complexity(data.new_password)

    user.set_password(data.new_password)
    user.save(update_fields=["password", "updated_at"])
    revoke_all_refresh_tokens(user)
    return {"message": "Password reset successful"}

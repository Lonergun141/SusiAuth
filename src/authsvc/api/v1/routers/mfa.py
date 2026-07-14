from django_ratelimit.decorators import ratelimit
from ninja import Router
from ninja.errors import HttpError

from authsvc.api.v1.auth import auth
from authsvc.api.v1.schemas import (
    MfaConfirmIn,
    MfaReauthIn,
    MfaSetupOut,
    MfaStatusOut,
    MfaVerifyIn,
    RecoveryCodesOut,
    TokenOut,
)
from authsvc.apps.accounts.models import User
from authsvc.apps.audit.models import AuditEvent
from authsvc.apps.audit.services import record_event
from authsvc.apps.common.security import verify_mfa_challenge
from authsvc.apps.mfa import services as mfa_services
from authsvc.apps.notifications import services as email_services
from authsvc.apps.tokens.services import issue_token_pair

router = Router(tags=["mfa"])


def _current_user(request) -> User:
    return User.objects.get(uuid=request.jwt["sub"])


@router.get("/status", response=MfaStatusOut, auth=auth)
def status(request):
    user = _current_user(request)
    return {
        "enabled": user.mfa_enabled,
        "recovery_codes_remaining": mfa_services.remaining_recovery_codes(user),
    }


@router.post("/setup", response=MfaSetupOut, auth=auth)
def setup(request):
    """Begin enrollment: returns the shared secret + otpauth URI (render as QR).

    Not active until confirmed with a valid code.
    """
    user = _current_user(request)
    secret, uri = mfa_services.start_enrollment(user)
    return {"secret": secret, "otpauth_uri": uri}


@router.post("/confirm", response=RecoveryCodesOut, auth=auth)
@ratelimit(key="ip", rate="10/m", block=True)
def confirm(request, data: MfaConfirmIn):
    """Confirm enrollment with a TOTP code; enables MFA and returns recovery
    codes (shown only once)."""
    user = _current_user(request)
    codes = mfa_services.confirm_enrollment(user, data.code)
    if codes is None:
        record_event(
            AuditEvent.EventType.MFA_ENROLLMENT,
            result=AuditEvent.Result.FAILURE,
            actor=user,
            target=user,
            request=request,
            metadata={"reason": "invalid_code"},
        )
        raise HttpError(400, "Invalid or expired code")
    email_services.send_mfa_enabled_email(user)
    record_event(
        AuditEvent.EventType.MFA_ENROLLMENT,
        actor=user,
        target=user,
        request=request,
    )
    return {"recovery_codes": codes}


@router.post("/disable", response={200: dict}, auth=auth)
@ratelimit(key="ip", rate="10/m", block=True)
def disable(request, data: MfaReauthIn):
    """Disable MFA. Requires re-auth: current password AND a valid code."""
    user = _current_user(request)
    if not user.mfa_enabled:
        raise HttpError(400, "MFA is not enabled")
    if not user.check_password(data.password):
        raise HttpError(400, "Password incorrect")
    if mfa_services.verify_factor(user, data.code) is None:
        raise HttpError(400, "Invalid code")
    mfa_services.disable(user)
    email_services.send_mfa_disabled_email(user)
    record_event(
        AuditEvent.EventType.MFA_REMOVAL,
        actor=user,
        target=user,
        request=request,
    )
    return {"message": "MFA disabled"}


@router.post("/recovery-codes", response=RecoveryCodesOut, auth=auth)
@ratelimit(key="ip", rate="5/m", block=True)
def regenerate_recovery_codes(request, data: MfaReauthIn):
    """Regenerate recovery codes (invalidates the old set). Requires re-auth."""
    user = _current_user(request)
    if not user.mfa_enabled:
        raise HttpError(400, "MFA is not enabled")
    if not user.check_password(data.password):
        raise HttpError(400, "Password incorrect")
    if mfa_services.verify_factor(user, data.code) is None:
        raise HttpError(400, "Invalid code")
    codes = mfa_services.regenerate_recovery_codes(user)
    return {"recovery_codes": codes}


@router.post("/verify", response=TokenOut)
@ratelimit(key="ip", rate="10/m", block=True)
def verify(request, data: MfaVerifyIn):
    """Second login step: exchange a valid MFA challenge + code for tokens."""
    payload = verify_mfa_challenge(data.mfa_token)
    if payload is None:
        raise HttpError(401, "Invalid or expired MFA session")

    try:
        user = User.objects.get(uuid=payload["sub"])
    except User.DoesNotExist:
        raise HttpError(401, "Invalid MFA session")

    factor = mfa_services.verify_factor(user, data.code)
    if factor is None:
        raise HttpError(401, "Invalid code")
    if factor == "recovery":
        email_services.send_mfa_recovery_used_email(user)
        record_event(
            AuditEvent.EventType.RECOVERY_CODE_USAGE,
            actor=user,
            target=user,
            request=request,
        )

    access, refresh = issue_token_pair(user, request)
    record_event(
        AuditEvent.EventType.LOGIN_SUCCESS,
        actor=user,
        target=user,
        request=request,
        metadata={"factor": factor},
    )
    return {"access_token": access, "refresh_token": refresh}

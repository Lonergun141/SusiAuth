from ninja import Schema
from pydantic import EmailStr


class RegistrationFieldOut(Schema):
    name: str
    label: str
    field_type: str
    required: bool
    options: list[str] = []

class RegisterIn(Schema):
    email: EmailStr
    password: str
    first_name: str | None = None
    last_name: str | None = None
    custom_fields: dict = {}

class VerifyEmailIn(Schema):
    email: EmailStr
    code: str

class ResendVerificationIn(Schema):
    email: EmailStr

class LoginIn(Schema):
    email: EmailStr
    password: str

class TokenOut(Schema):
    access_token: str
    refresh_token: str

class LoginOut(Schema):
    # Either tokens (no MFA) or an MFA challenge (mfa_required=True + mfa_token).
    mfa_required: bool = False
    access_token: str | None = None
    refresh_token: str | None = None
    mfa_token: str | None = None

class RefreshIn(Schema):
    refresh_token: str

class LogoutIn(Schema):
    refresh_token: str

class MeOut(Schema):
    id: int
    email: EmailStr
    first_name: str
    last_name: str
    is_email_verified: bool
    mfa_enabled: bool = False

class ChangePasswordIn(Schema):
    current_password: str
    new_password: str

class EmailIn(Schema):
    email: EmailStr

class ResetPasswordIn(Schema):
    token: str
    new_password: str

# --- MFA ---------------------------------------------------------------------
class MfaSetupOut(Schema):
    secret: str
    otpauth_uri: str

class MfaConfirmIn(Schema):
    code: str

class RecoveryCodesOut(Schema):
    recovery_codes: list[str]

class MfaStatusOut(Schema):
    enabled: bool
    recovery_codes_remaining: int

class MfaReauthIn(Schema):
    password: str
    code: str

class MfaVerifyIn(Schema):
    mfa_token: str
    code: str

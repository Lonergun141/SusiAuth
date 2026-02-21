from ninja import Schema
from pydantic import EmailStr, Field

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

class ChangePasswordIn(Schema):
    current_password: str
    new_password: str

class EmailIn(Schema):
    email: EmailStr

class ResetPasswordIn(Schema):
    token: str
    new_password: str

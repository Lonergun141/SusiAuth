from ninja import Schema
from typing import Optional

class RegisterIn(Schema):
    email: str
    password: str
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""

class LoginIn(Schema):
    email: str
    password: str

class TokenOut(Schema):
    access_token: str
    refresh_token: str

class RefreshIn(Schema):
    refresh_token: str

class LogoutIn(Schema):
    refresh_token: str

class VerifyEmailIn(Schema):
    token: str

class EmailIn(Schema):
    email: str

class ResetPasswordIn(Schema):
    token: str
    new_password: str

class ChangePasswordIn(Schema):
    current_password: str
    new_password: str

class MeOut(Schema):
    id: int
    email: str
    first_name: str
    last_name: str
    is_email_verified: bool

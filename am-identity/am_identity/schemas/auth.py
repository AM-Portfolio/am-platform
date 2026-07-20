from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
import re

_PASSWORD_POLICY = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")
_PHONE_POLICY = re.compile(r"^\+?[1-9]\d{9,14}$")


def _validate_password(value: str) -> str:
    if not _PASSWORD_POLICY.match(value):
        raise ValueError(
            "Password must be at least 8 characters and include upper, lower, and a digit"
        )
    return value


def _validate_phone(value: str) -> str:
    cleaned = re.sub(r"[\s\-()]", "", value.strip())
    if not _PHONE_POLICY.match(cleaned):
        raise ValueError("Phone must be 10–15 digits, optionally starting with +")
    return cleaned


def _require_token_or_code(token: str | None, code: str | None) -> None:
    has_token = bool(token and token.strip())
    has_code = bool(code and code.strip())
    if has_token == has_code:
        raise ValueError("Provide exactly one of token or code")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return _validate_password(value)

    @field_validator("phone")
    @classmethod
    def phone_policy(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _validate_phone(value)


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class OTPLoginRequest(BaseModel):
    username: str
    otp: str


class GoogleAuthURLRequest(BaseModel):
    redirect_uri: str


class GoogleAuthURLResponse(BaseModel):
    auth_url: str
    state: str
    expires_in: int


class GoogleCallbackRequest(BaseModel):
    code: str
    state: str
    redirect_uri: str


class GoogleTokenRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    expires_in: int
    refresh_expires_in: int | None = None
    refresh_token: str | None = None
    token_type: str = "Bearer"
    scope: str | None = None


class VerifyEmailConfirmResponse(TokenResponse):
    """Verify-email confirm verifies the mailbox and returns a login session."""

    status: str = "verified"
    user_id: str | None = None


class ServiceTokenRequest(BaseModel):
    audience: str | None = None


class ServiceTokenResponse(BaseModel):
    access_token: str
    expires_in: int
    token_type: str = "Bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str | None = None
    code: str | None = None
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return _validate_password(value)

    @model_validator(mode="after")
    def token_or_code(self) -> PasswordResetConfirmRequest:
        _require_token_or_code(self.token, self.code)
        return self


class VerifyEmailConfirmRequest(BaseModel):
    token: str | None = None
    code: str | None = None

    @model_validator(mode="after")
    def token_or_code(self) -> VerifyEmailConfirmRequest:
        _require_token_or_code(self.token, self.code)
        return self


class ResendVerifyEmailRequest(BaseModel):
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    email: EmailStr
    current_password: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return _validate_password(value)

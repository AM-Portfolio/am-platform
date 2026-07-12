from pydantic import BaseModel, EmailStr, Field, field_validator
import re


_PASSWORD_POLICY = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


def _validate_password(value: str) -> str:
    if not _PASSWORD_POLICY.match(value):
        raise ValueError(
            "Password must be at least 8 characters and include upper, lower, and a digit"
        )
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str | None = None
    last_name: str | None = None

    @field_validator("password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return _validate_password(value)

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


class ServiceTokenRequest(BaseModel):
    audience: str | None = None


class ServiceTokenResponse(BaseModel):
    access_token: str
    expires_in: int
    token_type: str = "Bearer"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, value: str) -> str:
        return _validate_password(value)


class VerifyEmailConfirmRequest(BaseModel):
    token: str


class ResendVerifyEmailRequest(BaseModel):
    email: EmailStr

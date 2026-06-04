from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    first_name: str | None = None
    last_name: str | None = None


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

from fastapi import APIRouter, Depends, status

from am_identity.deps import get_identity_provider
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.auth import (
    GoogleAuthURLRequest,
    GoogleAuthURLResponse,
    GoogleCallbackRequest,
    LoginRequest,
    LogoutRequest,
    OTPLoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: RegisterRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.create_user(payload)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.authenticate(payload.username, payload.password)


@router.post("/login/otp")
async def login_otp(
    payload: OTPLoginRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.authenticate_otp(payload.username, payload.otp)


@router.post("/google/url", response_model=GoogleAuthURLResponse)
async def google_auth_url(
    payload: GoogleAuthURLRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.build_google_auth_url(payload.redirect_uri)


@router.post("/google/callback", response_model=TokenResponse)
async def google_callback(
    payload: GoogleCallbackRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.authenticate_google(payload.code, payload.state, payload.redirect_uri)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.refresh_token(payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    await provider.revoke_token(payload.refresh_token)

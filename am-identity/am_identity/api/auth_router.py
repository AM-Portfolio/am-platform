from fastapi import APIRouter, Depends, status

from am_identity.deps import get_identity_provider
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.auth import (
    GoogleAuthURLRequest,
    GoogleAuthURLResponse,
    GoogleCallbackRequest,
    GoogleTokenRequest,
    LoginRequest,
    LogoutRequest,
    OTPLoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    ResendVerifyEmailRequest,
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


@router.post("/google/token", response_model=TokenResponse)
async def google_token(
    payload: GoogleTokenRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.authenticate_google_token(payload.id_token)


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


@router.post("/password-reset", status_code=status.HTTP_202_ACCEPTED)
async def password_reset(
    payload: PasswordResetRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    # Always 202 to avoid email enumeration.
    await provider.send_password_reset_email(payload.email)
    return {"status": "accepted"}


@router.post("/password-reset/confirm", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def password_reset_confirm(
    payload: PasswordResetConfirmRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    # Keycloak reset links complete in-browser via execute-actions-email.
    # Identity-owned token confirm is reserved for a later phase.
    _ = (payload, provider)
    return {
        "detail": (
            "Use the Keycloak reset link from email. "
            "Identity-owned token confirm is not implemented yet."
        )
    }


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED)
async def resend_verify_email(
    payload: ResendVerifyEmailRequest,
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    # Always 202 to avoid email enumeration.
    users = await provider.list_users(email=payload.email, first=0, max_results=1)
    if users:
        await provider.send_verify_email(users[0]["id"])
    return {"status": "accepted"}

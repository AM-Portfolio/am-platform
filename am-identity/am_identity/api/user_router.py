from datetime import datetime, timezone
from typing import Any
import httpx

from fastapi import APIRouter, Depends, HTTPException, status

from am_identity.core.config import get_settings
from am_identity.core.kafka import publish_event
from am_identity.deps import get_identity_provider
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.user import (
    AccountDeletionRequest,
    UpdateUserSettingsRequest,
    UserProfileResponse,
)
from am_platform_security import AuthContext, require_auth_context

router = APIRouter(prefix="/users", tags=["users"])


def _profile_from_claims(claims: dict[str, Any]) -> dict[str, Any]:
    """Build profile from validated JWT when Keycloak userinfo is unavailable."""
    return {
        "sub": claims.get("sub", ""),
        "email": claims.get("email"),
        "preferred_username": claims.get("preferred_username"),
        "given_name": claims.get("given_name"),
        "family_name": claims.get("family_name"),
        "settings": {},
    }


@router.get("/me", response_model=UserProfileResponse)
async def get_me(
    context: AuthContext = Depends(require_auth_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    try:
        user_info = await provider.get_current_user_info(context.access_token)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and context.claims.get(
            "sub"
        ):
            user_info = _profile_from_claims(context.claims)
        else:
            raise
    settings = await provider.get_user_settings(context.subject)

    deletion_pending = await provider.is_user_deletion_pending(context.subject)
    account_restored = False

    return UserProfileResponse(
        sub=user_info.get("sub", context.subject),
        email=user_info.get("email"),
        preferred_username=user_info.get("preferred_username"),
        given_name=user_info.get("given_name"),
        family_name=user_info.get("family_name"),
        roles=context.roles,
        settings=settings,
        deletion_pending=deletion_pending,
        account_restored=account_restored,
    )


@router.post("/me/request-deletion")
async def request_deletion(
    payload: AccountDeletionRequest,
    context: AuthContext = Depends(require_auth_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    await provider.set_user_attributes(
        context.subject,
        {
            "account_status": "pending_deletion",
            "deletion_requested_at": str(datetime.now(timezone.utc).timestamp()),
            "deletion_feedback": payload.feedback,
        },
    )

    await publish_event(
        topic="am.identity.events.v1",
        event_type="am.identity.deletion_requested.v1",
        payload={
            "user_id": context.subject,
            "email": context.claims.get("email", ""),
            "feedback": payload.feedback,
        },
    )

    return {"message": "Account scheduled for deletion in 90 days."}


@router.post("/me/restore")
async def restore_account(
    context: AuthContext = Depends(require_auth_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    restored = await provider.restore_user_account(context.subject)
    if not restored:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is not pending deletion or could not be restored.",
        )

    await publish_event(
        topic="am.identity.events.v1",
        event_type="am.identity.account_restored.v1",
        payload={
            "user_id": context.subject,
            "email": context.claims.get("email", ""),
        },
    )

    return {"message": "Account successfully restored."}


@router.patch("/me/settings")
async def update_my_settings(
    payload: UpdateUserSettingsRequest,
    context: AuthContext = Depends(require_auth_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.update_user_settings(context.subject, payload.settings)

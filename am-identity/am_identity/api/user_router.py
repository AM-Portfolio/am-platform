from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from am_identity.deps import get_identity_provider
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.user import UpdateUserSettingsRequest, UserProfileResponse
from am_platform_security import AuthContext, require_auth_context

router = APIRouter(prefix="/users", tags=["users"])


def _profile_from_claims(claims: dict[str, Any]) -> dict[str, Any]:
    """Build profile from validated JWT when Keycloak userinfo is unavailable."""
    return {
        "sub": claims.get("userId") or claims.get("sub", ""),
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
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and context.claims.get("sub"):
            user_info = _profile_from_claims(context.claims)
        else:
            raise
    settings = await provider.get_user_settings(context.subject)
    return UserProfileResponse(
        sub=user_info.get("sub", context.subject),
        email=user_info.get("email"),
        preferred_username=user_info.get("preferred_username"),
        given_name=user_info.get("given_name"),
        family_name=user_info.get("family_name"),
        roles=context.roles,
        settings=settings,
    )


@router.patch("/me/settings")
async def update_my_settings(
    payload: UpdateUserSettingsRequest,
    context: AuthContext = Depends(require_auth_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.update_user_settings(context.subject, payload.settings)

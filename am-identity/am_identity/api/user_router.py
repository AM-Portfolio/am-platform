from datetime import datetime, timezone
from typing import Any
import httpx

from fastapi import APIRouter, Depends, HTTPException, status

from am_identity.core.config import get_settings
from am_identity.core.kafka import publish_event
from am_identity.deps import get_identity_provider
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.user import AccountDeletionRequest, UpdateUserSettingsRequest, UserProfileResponse
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
        if exc.status_code == status.HTTP_401_UNAUTHORIZED and context.claims.get("sub"):
            user_info = _profile_from_claims(context.claims)
        else:
            raise
    settings = await provider.get_user_settings(context.subject)

    deletion_pending = False
    account_restored = False
    admin_token = await provider._get_admin_access_token() if hasattr(provider, '_get_admin_access_token') else ""
    if admin_token:
        user = await provider.get_user(context.subject)
        attrs = user.get("attributes", {}) if isinstance(user.get("attributes"), dict) else {}
        
        settings_conf = get_settings()
        admin_users_url = f"{settings_conf.keycloak_url.rstrip('/')}/admin/realms/{settings_conf.keycloak_realm}/users"
        
        async with httpx.AsyncClient(timeout=20.0, verify=settings_conf.verify_ssl) as client:
            get_response = await client.get(f"{admin_users_url}/{context.subject}", headers={"Authorization": f"Bearer {admin_token}"})
            if get_response.status_code < 400:
                raw_user = get_response.json()
                raw_attrs = raw_user.get("attributes", {})
                if raw_attrs.get("account_status") == ["pending_deletion"]:
                    deletion_pending = True
                    await provider.remove_user_attribute(context.subject, "account_status")
                    await provider.remove_user_attribute(context.subject, "deletion_requested_at")
                    await provider.remove_user_attribute(context.subject, "deletion_feedback")
                    account_restored = True
                    deletion_pending = False

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
    await provider.set_user_attribute(context.subject, "account_status", "pending_deletion")
    await provider.set_user_attribute(context.subject, "deletion_requested_at", str(datetime.now(timezone.utc).timestamp()))
    await provider.set_user_attribute(context.subject, "deletion_feedback", payload.feedback)
    
    await publish_event(
        topic="am.identity.events.v1",
        event_type="am.identity.deletion_requested.v1",
        payload={
            "user_id": context.subject,
            "email": context.claims.get("email", ""),
            "feedback": payload.feedback,
        }
    )
    
    return {"message": "Account scheduled for deletion in 90 days."}


@router.patch("/me/settings")
async def update_my_settings(
    payload: UpdateUserSettingsRequest,
    context: AuthContext = Depends(require_auth_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return await provider.update_user_settings(context.subject, payload.settings)

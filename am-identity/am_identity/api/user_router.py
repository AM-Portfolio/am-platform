from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from am_identity.deps import get_identity_provider
from am_identity.api.auth_deps import require_user_context
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.security import LoginSessionResponse, SecurityEventResponse
from am_identity.schemas.user import UpdateUserSettingsRequest, UserProfileResponse
from am_identity.services.login_session_service import login_session_service
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


@router.get("/me/security-events", response_model=list[SecurityEventResponse])
async def list_security_events(
    context: AuthContext = Depends(require_user_context()),
    since: float | None = Query(default=None),
) -> list[SecurityEventResponse]:
    events = login_session_service.list_security_events(context.subject, since=since)
    return [
        SecurityEventResponse(
            event_id=event.event_id,
            type=event.type,
            session_id=event.session_id,
            device_label=event.device_label,
            geo_city=event.geo_city,
            geo_country=event.geo_country,
            created_at=event.created_at,
            acknowledged=event.acknowledged,
        )
        for event in events
    ]


@router.post("/me/security-events/{event_id}/ack", response_model=SecurityEventResponse)
async def acknowledge_security_event(
    event_id: str,
    context: AuthContext = Depends(require_user_context()),
) -> SecurityEventResponse:
    event = login_session_service.acknowledge_security_event(context.subject, event_id)
    return SecurityEventResponse(
        event_id=event.event_id,
        type=event.type,
        session_id=event.session_id,
        device_label=event.device_label,
        geo_city=event.geo_city,
        geo_country=event.geo_country,
        created_at=event.created_at,
        acknowledged=event.acknowledged,
    )


@router.get("/me/login-sessions", response_model=list[LoginSessionResponse])
async def list_login_sessions(
    context: AuthContext = Depends(require_user_context()),
) -> list[LoginSessionResponse]:
    sessions = login_session_service.list_login_sessions(context.subject)
    return [
        LoginSessionResponse(
            session_id=session.session_id,
            browser=session.browser,
            os=session.os,
            client_type=session.client_type,
            geo_city=session.geo_city,
            geo_country=session.geo_country,
            ip_masked=session.ip_masked,
            machine_label=session.machine_label,
            created_at=session.created_at,
            last_active_at=session.last_active_at,
        )
        for session in sessions
    ]


@router.delete("/me/login-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_login_session(
    session_id: str,
    context: AuthContext = Depends(require_user_context()),
) -> None:
    login_session_service.revoke_login_session(context.subject, session_id)


@router.delete("/me/login-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_login_sessions(
    context: AuthContext = Depends(require_user_context()),
) -> None:
    login_session_service.revoke_all_login_sessions(context.subject)

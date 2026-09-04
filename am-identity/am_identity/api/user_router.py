from datetime import datetime, timezone
from typing import Any
import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from am_identity.core.config import get_settings
from am_identity.core.kafka import publish_event
from am_identity.deps import get_identity_provider
from am_identity.api.auth_deps import require_user_context
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.security import LoginSessionResponse, SecurityEventResponse
from am_identity.schemas.user import UpdateUserSettingsRequest, UserProfileResponse
from am_identity.services.bff_session_service import bff_session_service
from am_identity.services.cookie_utils import clear_session_cookie
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
    request: Request,
    context: AuthContext = Depends(require_user_context()),
) -> list[LoginSessionResponse]:
    sessions = login_session_service.list_login_sessions(context.subject)
    sid = context.claims.get("sid")
    current_sid = sid if isinstance(sid, str) else None
    cookie_session_id = request.cookies.get(bff_session_service.SESSION_COOKIE)
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
            current=(
                (current_sid is not None and session.keycloak_session_id == current_sid)
                or (
                    cookie_session_id is not None
                    and session.bff_session_id == cookie_session_id
                )
            ),
        )
        for session in sessions
    ]


@router.delete("/me/login-sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_login_session(
    session_id: str,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_user_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
) -> None:
    session = login_session_service.get_login_session(context.subject, session_id)
    cookie_session_id = request.cookies.get(bff_session_service.SESSION_COOKIE)
    sid = context.claims.get("sid")
    current_sid = sid if isinstance(sid, str) else None
    is_current = (
        (current_sid is not None and session.keycloak_session_id == current_sid)
        or (
            cookie_session_id is not None
            and session.bff_session_id == cookie_session_id
        )
    )
    if session.keycloak_session_id:
        await provider.logout_keycloak_session(session.keycloak_session_id)
    if session.bff_session_id:
        bff_session_service.delete_session(session.bff_session_id)
    login_session_service.revoke_login_session(context.subject, session_id)
    if is_current:
        clear_session_cookie(response)


@router.delete("/me/login-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_login_sessions(
    response: Response,
    context: AuthContext = Depends(require_user_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
) -> None:
    await provider.logout_user_sessions(context.subject)
    bff_session_service.delete_sessions_for_user(context.subject)
    login_session_service.revoke_all_login_sessions(context.subject)
    clear_session_cookie(response)

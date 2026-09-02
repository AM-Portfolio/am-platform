from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from am_identity.deps import get_identity_provider
from am_identity.email.rate_limit import client_ip, enforce_rate_limit
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.device_link import (
    DeviceLinkApproveRequest,
    DeviceLinkApproveResponse,
    DeviceLinkDenyRequest,
    DeviceLinkPreviewResponse,
    DeviceLinkStartRequest,
    DeviceLinkStartResponse,
    DeviceLinkStatusResponse,
    DeviceLinkUserResponse,
    WebSessionTokensResponse,
)
from am_identity.services.bff_session_service import BffUser
from am_identity.services.cookie_utils import set_session_cookie
from am_identity.services.device_link_service import (
    DEVICE_LINK_TTL_SECONDS,
    POLL_INTERVAL_MS,
    DeviceLinkStartInput,
    device_link_service,
)
from am_identity.services.login_session_service import LoginContext, login_session_service
from am_identity.services.web_session_tokens import issue_web_session_tokens
from am_platform_security import AuthContext, require_auth_context

router = APIRouter(prefix="/auth/device-link", tags=["device-link"])

_DEVICE_LINK_STATUS_POLL_BUDGET = (DEVICE_LINK_TTL_SECONDS * 1000) // POLL_INTERVAL_MS + 5


def _bff_user_from_context(context: AuthContext) -> BffUser:
    claims = context.claims
    return BffUser(
        sub=context.subject,
        email=claims.get("email"),
        preferred_username=claims.get("preferred_username"),
        given_name=claims.get("given_name"),
        family_name=claims.get("family_name"),
    )


async def _web_tokens_for_user(
    provider: IIdentityProvider,
    user_id: str,
) -> tuple[str, str | None, int | None]:
    return await issue_web_session_tokens(provider, user_id)


@router.post("/start", response_model=DeviceLinkStartResponse)
async def start_device_link(payload: DeviceLinkStartRequest, request: Request) -> DeviceLinkStartResponse:
    enforce_rate_limit(request, name="device-link-start", limit=10)
    record = device_link_service.start(
        DeviceLinkStartInput(
            client=payload.client,
            redirect_hint=payload.redirect_hint,
            code_challenge=payload.code_challenge,
            browser=payload.browser,
            os=payload.os,
            ip=client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    )
    return DeviceLinkStartResponse(
        device_link_id=record.device_link_id,
        qr_payload=device_link_service.build_qr_payload(record),
        confirmation_code=record.confirmation_code,
        expires_at=record.expires_at,
    )


@router.get("/{device_link_id}/status", response_model=DeviceLinkStatusResponse)
async def device_link_status(
    device_link_id: str,
    request: Request,
    response: Response,
    code_verifier: str,
) -> DeviceLinkStatusResponse:
    enforce_rate_limit(
        request,
        name="device-link-status",
        key_suffix=device_link_id,
        limit=_DEVICE_LINK_STATUS_POLL_BUDGET,
        window_seconds=DEVICE_LINK_TTL_SECONDS,
    )
    record, user = device_link_service.poll_status(
        device_link_id,
        code_verifier=code_verifier,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    user_response: DeviceLinkUserResponse | None = None
    tokens_response: WebSessionTokensResponse | None = None
    if user is not None and record.session_id is not None:
        from am_identity.services.bff_session_service import bff_session_service

        bff_session = bff_session_service.get_session(record.session_id)
        if bff_session is not None:
            set_session_cookie(response, bff_session)
            login_session_service.record_login(
                LoginContext(
                    user_id=user.sub,
                    email=user.email,
                    client_type="web",
                    browser=record.browser,
                    os=record.os,
                    ip=record.ip,
                    user_agent=record.user_agent,
                    machine_label=record.machine_label,
                    machine_trust_key=request.headers.get("x-machine-trust-key"),
                    bff_session_id=record.session_id,
                    access_token=record.access_token,
                    refresh_token=record.refresh_token,
                )
            )
        user_response = DeviceLinkUserResponse(
            sub=user.sub,
            email=user.email,
            preferred_username=user.preferred_username,
        )
        if record.access_token:
            tokens_response = WebSessionTokensResponse(
                access_token=record.access_token,
                refresh_token=record.refresh_token,
            )
    return DeviceLinkStatusResponse(
        status=record.status,
        user=user_response,
        tokens=tokens_response,
    )


@router.get("/{device_link_id}/preview", response_model=DeviceLinkPreviewResponse)
async def device_link_preview(
    device_link_id: str,
    context: AuthContext = Depends(require_auth_context()),
) -> DeviceLinkPreviewResponse:
    preview = device_link_service.preview(device_link_id, user_id=context.subject)
    return DeviceLinkPreviewResponse(**preview)


@router.post("/{device_link_id}/approve", response_model=DeviceLinkApproveResponse)
async def device_link_approve(
    device_link_id: str,
    payload: DeviceLinkApproveRequest,
    request: Request,
    context: AuthContext = Depends(require_auth_context()),
    provider: IIdentityProvider = Depends(get_identity_provider),
) -> DeviceLinkApproveResponse:
    enforce_rate_limit(request, name="device-link-approve", limit=5)
    user = _bff_user_from_context(context)
    access_token, refresh_token, _expires_in = await _web_tokens_for_user(provider, user.sub)
    record = device_link_service.approve(
        device_link_id,
        user=user,
        confirmation_code=payload.confirmation_code,
        device_name=payload.device_name,
        machine_label=payload.machine_label,
        access_token=access_token,
        refresh_token=refresh_token,
    )
    return DeviceLinkApproveResponse(status=record.status)


@router.post("/{device_link_id}/deny", status_code=status.HTTP_204_NO_CONTENT)
async def device_link_deny(
    device_link_id: str,
    payload: DeviceLinkDenyRequest,
    request: Request,
    context: AuthContext = Depends(require_auth_context()),
) -> Response:
    device_link_service.deny(
        device_link_id,
        user_id=context.subject,
        reason=payload.reason,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{device_link_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def device_link_cancel(device_link_id: str) -> Response:
    device_link_service.cancel(device_link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

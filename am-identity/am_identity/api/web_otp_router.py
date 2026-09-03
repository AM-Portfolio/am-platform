from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from am_identity.deps import get_identity_provider
from am_identity.email.rate_limit import client_ip, enforce_rate_limit
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.web_otp import (
    WebOtpSendRequest,
    WebOtpSendResponse,
    WebOtpVerifyRequest,
    WebOtpVerifyResponse,
    WebOtpVerifyTokensResponse,
    WebOtpVerifyUserResponse,
)
from am_identity.services.bff_session_service import bff_session_service
from am_identity.services.cookie_utils import set_session_cookie
from am_identity.services.user_agent import is_web_user_agent
from am_identity.services.web_otp_service import web_otp_service
from am_identity.services.web_session_tokens import issue_web_session_tokens

router = APIRouter(prefix="/auth/web/otp", tags=["web-otp"])

_TRUSTED_WEB_ORIGIN = re.compile(
    r"^https?://(localhost(:\d+)?|127\.0\.0\.1(:\d+)?|.*\.asrax\.in)(/.*)?$",
    re.IGNORECASE,
)


def _require_web_user_agent(request: Request) -> None:
    origin = (request.headers.get("origin") or "").strip()
    if origin and _TRUSTED_WEB_ORIGIN.match(origin):
        return
    user_agent = request.headers.get("user-agent")
    if not is_web_user_agent(user_agent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Web OTP login is available on web browsers only",
        )


async def _resolve_user(
    provider: IIdentityProvider,
    channel: str,
    destination: str,
) -> dict[str, str] | None:
    if channel == "email":
        users = await provider.list_users(email=destination, first=0, max_results=1)
    else:
        users = await provider.list_users(search=destination, first=0, max_results=1)
    if not users:
        return None
    user = users[0]
    return {
        "id": user.get("id", ""),
        "email": user.get("email"),
    }


@router.post("/send", response_model=WebOtpSendResponse)
async def web_otp_send(
    payload: WebOtpSendRequest,
    request: Request,
    provider: IIdentityProvider = Depends(get_identity_provider),
) -> WebOtpSendResponse:
    _require_web_user_agent(request)
    enforce_rate_limit(request, name="web-otp-send", limit=10)
    session = await web_otp_service.send(
        channel=payload.channel,
        destination=payload.destination,
        resolve_user_id=lambda channel, destination: _resolve_user(provider, channel, destination),
    )
    return WebOtpSendResponse(
        otp_session_id=session.otp_session_id,
        expires_at=session.expires_at,
        masked_destination=web_otp_service.mask_destination(session),
    )


@router.post("/verify", response_model=WebOtpVerifyResponse)
async def web_otp_verify(
    payload: WebOtpVerifyRequest,
    request: Request,
    response: Response,
    provider: IIdentityProvider = Depends(get_identity_provider),
) -> WebOtpVerifyResponse:
    _require_web_user_agent(request)
    pending = web_otp_service.pending_session(payload.otp_session_id)
    access_token, refresh_token, expires_in = await issue_web_session_tokens(
        provider,
        pending.user_id,
    )
    user, session_id = web_otp_service.verify(
        otp_session_id=payload.otp_session_id,
        code=payload.code,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
        access_token=access_token,
        refresh_token=refresh_token,
        machine_trust_key=request.headers.get("x-machine-trust-key"),
    )
    bff_session = bff_session_service.get_session(session_id)
    if bff_session is not None:
        set_session_cookie(response, bff_session)
    return WebOtpVerifyResponse(
        user=WebOtpVerifyUserResponse(
            sub=user.sub,
            email=user.email,
            preferred_username=user.preferred_username,
        ),
        tokens=WebOtpVerifyTokensResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
        ),
    )

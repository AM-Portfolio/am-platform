from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, status

from am_identity.schemas.session import BffMeResponse
from am_identity.services.bff_session_service import bff_session_service
from am_identity.services.cookie_utils import read_session_cookie

router = APIRouter(prefix="/bff", tags=["bff"])


@router.get("/me", response_model=BffMeResponse)
async def bff_me(am_session: str | None = Cookie(default=None)) -> BffMeResponse:
    session = read_session_cookie(am_session)
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session not found")
    user = session.user
    return BffMeResponse(
        sub=user.sub,
        email=user.email,
        preferred_username=user.preferred_username,
        given_name=user.given_name,
        family_name=user.family_name,
    )


@router.get("/audit")
async def bff_audit() -> dict[str, list[dict[str, object]]]:
    entries = bff_session_service.list_audit()
    return {
        "entries": [
            {
                "event": entry.event,
                "session_id": entry.session_id,
                "user_id": entry.user_id,
                "ip": entry.ip,
                "user_agent": entry.user_agent,
                "at": entry.at,
            }
            for entry in entries
        ]
    }

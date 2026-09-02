from __future__ import annotations

from fastapi import Response

from am_identity.core.config import IdentitySettings, get_settings
from am_identity.services.bff_session_service import BffSession, bff_session_service


def set_session_cookie(response: Response, session: BffSession, settings: IdentitySettings | None = None) -> None:
    resolved = settings or get_settings()
    secure = resolved.app_env not in ("dev", "local", "test")
    response.set_cookie(
        key=bff_session_service.SESSION_COOKIE,
        value=session.session_id,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )


def read_session_cookie(session_id: str | None) -> BffSession | None:
    return bff_session_service.get_session(session_id)

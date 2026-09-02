from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Literal

AuditEvent = Literal[
    "started",
    "scanned",
    "previewed",
    "approved",
    "denied",
    "expired",
    "poll_success",
    "cancelled",
]


@dataclass(frozen=True, slots=True)
class BffUser:
    sub: str
    email: str | None
    preferred_username: str | None = None
    given_name: str | None = None
    family_name: str | None = None


@dataclass(frozen=True, slots=True)
class BffSession:
    session_id: str
    user: BffUser
    access_token: str
    refresh_token: str | None
    created_at: float


@dataclass(frozen=True, slots=True)
class BffAuditEntry:
    event: AuditEvent | str
    session_id: str | None
    user_id: str | None
    ip: str | None
    user_agent: str | None
    at: float


class BffSessionService:
    SESSION_COOKIE = "am_session"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, BffSession] = {}
        self._audit: list[BffAuditEntry] = []

    def create_session(
        self,
        *,
        user: BffUser,
        access_token: str,
        refresh_token: str | None,
    ) -> BffSession:
        session_id = secrets.token_urlsafe(32)
        session = BffSession(
            session_id=session_id,
            user=user,
            access_token=access_token,
            refresh_token=refresh_token,
            created_at=time.time(),
        )
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str | None) -> BffSession | None:
        if not session_id:
            return None
        with self._lock:
            return self._sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def append_audit(
        self,
        *,
        event: AuditEvent | str,
        session_id: str | None = None,
        user_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        entry = BffAuditEntry(
            event=event,
            session_id=session_id,
            user_id=user_id,
            ip=ip,
            user_agent=user_agent,
            at=time.time(),
        )
        with self._lock:
            self._audit.append(entry)

    def list_audit(self) -> tuple[BffAuditEntry, ...]:
        with self._lock:
            return tuple(self._audit)


bff_session_service = BffSessionService()

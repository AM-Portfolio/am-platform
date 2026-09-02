from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status

from am_identity.services.device_link_service import compute_machine_trust_key
from am_identity.services.user_agent import device_class_from_user_agent, parse_os_family

SecurityEventType = Literal["new_device_login"]
ClientType = Literal["web", "android", "ios", "unknown"]


@dataclass(frozen=True, slots=True)
class KnownDevice:
    physical_device_id: str
    user_id: str
    machine_trust_key: str
    client_type: ClientType
    device_label: str | None
    first_seen_at: float
    last_seen_at: float
    geo_city: str | None
    geo_country: str | None


@dataclass(frozen=True, slots=True)
class LoginSession:
    session_id: str
    user_id: str
    physical_device_id: str
    browser: str | None
    os: str | None
    client_type: ClientType
    geo_city: str | None
    geo_country: str | None
    ip_masked: str | None
    machine_label: str | None
    keycloak_session_id: str | None
    created_at: float
    last_active_at: float
    revoked: bool = False


@dataclass(frozen=True, slots=True)
class SecurityEvent:
    event_id: str
    user_id: str
    type: SecurityEventType
    session_id: str | None
    device_label: str | None
    geo_city: str | None
    geo_country: str | None
    created_at: float
    acknowledged: bool = False


@dataclass(frozen=True, slots=True)
class LoginContext:
    user_id: str
    email: str | None
    client_type: ClientType
    browser: str | None
    os: str | None
    ip: str | None
    user_agent: str | None
    machine_label: str | None = None
    machine_trust_key: str | None = None
    bff_session_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    keycloak_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class LoginRecordResult:
    is_new_device: bool
    login_session: LoginSession
    security_event: SecurityEvent | None


def _mask_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    return ip


class LoginSessionService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._known_devices: dict[tuple[str, str], KnownDevice] = {}
        self._login_sessions: dict[str, LoginSession] = {}
        self._security_events: dict[str, SecurityEvent] = {}

    def record_login(self, ctx: LoginContext) -> LoginRecordResult:
        os_family = ctx.os or parse_os_family(ctx.user_agent)
        device_class = device_class_from_user_agent(ctx.user_agent)
        machine_trust_key = ctx.machine_trust_key or compute_machine_trust_key(
            user_id=ctx.user_id,
            ip=ctx.ip,
            os_family=os_family,
            device_class=device_class,
        )
        now = time.time()
        known_key = (ctx.user_id, machine_trust_key)
        is_new_device = False
        with self._lock:
            known = self._known_devices.get(known_key)
            if known is None:
                is_new_device = True
                physical_device_id = str(uuid.uuid4())
                known = KnownDevice(
                    physical_device_id=physical_device_id,
                    user_id=ctx.user_id,
                    machine_trust_key=machine_trust_key,
                    client_type=ctx.client_type,
                    device_label=ctx.machine_label,
                    first_seen_at=now,
                    last_seen_at=now,
                    geo_city=None,
                    geo_country=None,
                )
                self._known_devices[known_key] = known
            else:
                physical_device_id = known.physical_device_id
                updated = KnownDevice(
                    physical_device_id=known.physical_device_id,
                    user_id=known.user_id,
                    machine_trust_key=known.machine_trust_key,
                    client_type=known.client_type,
                    device_label=ctx.machine_label or known.device_label,
                    first_seen_at=known.first_seen_at,
                    last_seen_at=now,
                    geo_city=known.geo_city,
                    geo_country=known.geo_country,
                )
                self._known_devices[known_key] = updated
                known = updated

        session_id = str(uuid.uuid4())
        login_session = LoginSession(
            session_id=session_id,
            user_id=ctx.user_id,
            physical_device_id=physical_device_id,
            browser=ctx.browser,
            os=os_family,
            client_type=ctx.client_type,
            geo_city=None,
            geo_country=None,
            ip_masked=_mask_ip(ctx.ip),
            machine_label=ctx.machine_label,
            keycloak_session_id=ctx.keycloak_session_id,
            created_at=now,
            last_active_at=now,
        )
        security_event: SecurityEvent | None = None
        if is_new_device:
            event_id = str(uuid.uuid4())
            label = ctx.machine_label or ctx.browser or ctx.client_type
            security_event = SecurityEvent(
                event_id=event_id,
                user_id=ctx.user_id,
                type="new_device_login",
                session_id=session_id,
                device_label=label,
                geo_city=None,
                geo_country=None,
                created_at=now,
            )
            with self._lock:
                self._security_events[event_id] = security_event

        with self._lock:
            self._login_sessions[session_id] = login_session

        return LoginRecordResult(
            is_new_device=is_new_device,
            login_session=login_session,
            security_event=security_event,
        )

    def list_security_events(
        self,
        user_id: str,
        *,
        since: float | None = None,
        include_acknowledged: bool = False,
    ) -> tuple[SecurityEvent, ...]:
        with self._lock:
            events = [
                event
                for event in self._security_events.values()
                if event.user_id == user_id
                and (include_acknowledged or not event.acknowledged)
                and (since is None or event.created_at >= since)
            ]
        return tuple(sorted(events, key=lambda item: item.created_at, reverse=True))

    def acknowledge_security_event(self, user_id: str, event_id: str) -> SecurityEvent:
        with self._lock:
            event = self._security_events.get(event_id)
            if event is None or event.user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
            updated = SecurityEvent(
                event_id=event.event_id,
                user_id=event.user_id,
                type=event.type,
                session_id=event.session_id,
                device_label=event.device_label,
                geo_city=event.geo_city,
                geo_country=event.geo_country,
                created_at=event.created_at,
                acknowledged=True,
            )
            self._security_events[event_id] = updated
            return updated

    def list_login_sessions(self, user_id: str) -> tuple[LoginSession, ...]:
        with self._lock:
            sessions = [
                session
                for session in self._login_sessions.values()
                if session.user_id == user_id and not session.revoked
            ]
        return tuple(sorted(sessions, key=lambda item: item.last_active_at, reverse=True))

    def revoke_login_session(self, user_id: str, session_id: str) -> None:
        with self._lock:
            session = self._login_sessions.get(session_id)
            if session is None or session.user_id != user_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
            self._login_sessions[session_id] = LoginSession(
                session_id=session.session_id,
                user_id=session.user_id,
                physical_device_id=session.physical_device_id,
                browser=session.browser,
                os=session.os,
                client_type=session.client_type,
                geo_city=session.geo_city,
                geo_country=session.geo_country,
                ip_masked=session.ip_masked,
                machine_label=session.machine_label,
                keycloak_session_id=session.keycloak_session_id,
                created_at=session.created_at,
                last_active_at=session.last_active_at,
                revoked=True,
            )

    def revoke_all_login_sessions(self, user_id: str) -> int:
        count = 0
        with self._lock:
            for session_id, session in list(self._login_sessions.items()):
                if session.user_id != user_id or session.revoked:
                    continue
                self._login_sessions[session_id] = LoginSession(
                    session_id=session.session_id,
                    user_id=session.user_id,
                    physical_device_id=session.physical_device_id,
                    browser=session.browser,
                    os=session.os,
                    client_type=session.client_type,
                    geo_city=session.geo_city,
                    geo_country=session.geo_country,
                    ip_masked=session.ip_masked,
                    machine_label=session.machine_label,
                    keycloak_session_id=session.keycloak_session_id,
                    created_at=session.created_at,
                    last_active_at=session.last_active_at,
                    revoked=True,
                )
                count += 1
        return count


login_session_service = LoginSessionService()

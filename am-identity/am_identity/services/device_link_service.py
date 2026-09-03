from __future__ import annotations

import hashlib
import ipaddress
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status

from am_identity.services.bff_session_service import (
    AuditEvent,
    BffUser,
    bff_session_service,
)
from am_identity.services.pkce import verify_pkce

DeviceLinkStatus = Literal["pending", "approved", "cancelled", "expired", "consumed"]

DEVICE_LINK_TTL_SECONDS = 120
POLL_INTERVAL_MS = 2000


@dataclass(frozen=True, slots=True)
class DeviceLinkStartInput:
    client: str
    redirect_hint: str
    code_challenge: str
    browser: str | None
    os: str | None
    ip: str | None
    user_agent: str | None
    geo_city: str | None = None
    geo_country: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceLinkRecord:
    device_link_id: str
    status: DeviceLinkStatus
    code_challenge: str
    confirmation_code: str
    redirect_hint: str
    browser: str | None
    os: str | None
    geo_city: str | None
    geo_country: str | None
    ip: str | None
    user_agent: str | None
    created_at: float
    expires_at: float
    approved_user: BffUser | None = None
    approved_device_name: str | None = None
    machine_label: str | None = None
    session_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceLinkAuditEntry:
    device_link_id: str
    event: AuditEvent
    ip: str | None
    user_agent: str | None
    user_id: str | None
    at: float


def _generate_confirmation_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _mask_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv4Address):
            parts = ip.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
        return ip
    except ValueError:
        return ip


class DeviceLinkService:
    def __init__(self, *, ttl_seconds: int = DEVICE_LINK_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._links: dict[str, DeviceLinkRecord] = {}
        self._audit: list[DeviceLinkAuditEntry] = []

    def _now(self) -> float:
        return time.time()

    def _append_audit(
        self,
        *,
        device_link_id: str,
        event: AuditEvent,
        ip: str | None = None,
        user_agent: str | None = None,
        user_id: str | None = None,
    ) -> None:
        entry = DeviceLinkAuditEntry(
            device_link_id=device_link_id,
            event=event,
            ip=ip,
            user_agent=user_agent,
            user_id=user_id,
            at=self._now(),
        )
        with self._lock:
            self._audit.append(entry)
        bff_session_service.append_audit(
            event=event,
            user_id=user_id,
            ip=ip,
            user_agent=user_agent,
        )

    def _get_record(self, device_link_id: str) -> DeviceLinkRecord:
        with self._lock:
            record = self._links.get(device_link_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device link not found")
        if record.status not in ("consumed", "cancelled") and self._now() >= record.expires_at:
            expired = DeviceLinkRecord(
                device_link_id=record.device_link_id,
                status="expired",
                code_challenge=record.code_challenge,
                confirmation_code=record.confirmation_code,
                redirect_hint=record.redirect_hint,
                browser=record.browser,
                os=record.os,
                geo_city=record.geo_city,
                geo_country=record.geo_country,
                ip=record.ip,
                user_agent=record.user_agent,
                created_at=record.created_at,
                expires_at=record.expires_at,
            )
            with self._lock:
                self._links[device_link_id] = expired
            self._append_audit(
                device_link_id=device_link_id,
                event="expired",
                ip=record.ip,
                user_agent=record.user_agent,
            )
            return expired
        return record

    def _store(self, record: DeviceLinkRecord) -> None:
        with self._lock:
            self._links[record.device_link_id] = record

    def start(self, payload: DeviceLinkStartInput) -> DeviceLinkRecord:
        now = self._now()
        device_link_id = str(uuid.uuid4())
        confirmation_code = _generate_confirmation_code()
        record = DeviceLinkRecord(
            device_link_id=device_link_id,
            status="pending",
            code_challenge=payload.code_challenge,
            confirmation_code=confirmation_code,
            redirect_hint=payload.redirect_hint,
            browser=payload.browser,
            os=payload.os,
            geo_city=payload.geo_city,
            geo_country=payload.geo_country,
            ip=payload.ip,
            user_agent=payload.user_agent,
            created_at=now,
            expires_at=now + self._ttl_seconds,
        )
        self._store(record)
        self._append_audit(
            device_link_id=device_link_id,
            event="started",
            ip=payload.ip,
            user_agent=payload.user_agent,
        )
        return record

    def build_qr_payload(self, record: DeviceLinkRecord) -> dict[str, str | int]:
        return {
            "v": 1,
            "type": "am_device_link",
            "id": record.device_link_id,
            "host": record.redirect_hint,
        }

    def preview(self, device_link_id: str, *, user_id: str) -> dict[str, object]:
        record = self._get_record(device_link_id)
        if record.status == "expired":
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Device link expired")
        if record.status in ("cancelled", "consumed"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device link unavailable")
        self._append_audit(
            device_link_id=device_link_id,
            event="previewed",
            ip=record.ip,
            user_agent=record.user_agent,
            user_id=user_id,
        )
        return {
            "host": record.redirect_hint,
            "confirmation_code": record.confirmation_code,
            "browser": record.browser,
            "os": record.os,
            "geo_city": record.geo_city,
            "geo_country": record.geo_country,
            "ip_masked": _mask_ip(record.ip),
            "is_new_device": True,
            "requested_at": record.created_at,
        }

    def approve(
        self,
        device_link_id: str,
        *,
        user: BffUser,
        confirmation_code: str,
        device_name: str | None,
        machine_label: str | None,
        access_token: str,
        refresh_token: str | None,
    ) -> DeviceLinkRecord:
        record = self._get_record(device_link_id)
        if record.status == "expired":
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="Device link expired")
        if record.status != "pending":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device link already used")
        if not secrets.compare_digest(record.confirmation_code, confirmation_code.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid confirmation code",
            )
        approved = DeviceLinkRecord(
            device_link_id=record.device_link_id,
            status="approved",
            code_challenge=record.code_challenge,
            confirmation_code=record.confirmation_code,
            redirect_hint=record.redirect_hint,
            browser=record.browser,
            os=record.os,
            geo_city=record.geo_city,
            geo_country=record.geo_country,
            ip=record.ip,
            user_agent=record.user_agent,
            created_at=record.created_at,
            expires_at=record.expires_at,
            approved_user=user,
            approved_device_name=device_name,
            machine_label=machine_label,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        self._store(approved)
        self._append_audit(
            device_link_id=device_link_id,
            event="approved",
            ip=record.ip,
            user_agent=record.user_agent,
            user_id=user.sub,
        )
        return approved

    def deny(
        self,
        device_link_id: str,
        *,
        user_id: str,
        reason: str | None,
        ip: str | None,
        user_agent: str | None,
    ) -> None:
        record = self._get_record(device_link_id)
        if record.status in ("consumed", "cancelled", "expired"):
            return
        cancelled = DeviceLinkRecord(
            device_link_id=record.device_link_id,
            status="cancelled",
            code_challenge=record.code_challenge,
            confirmation_code=record.confirmation_code,
            redirect_hint=record.redirect_hint,
            browser=record.browser,
            os=record.os,
            geo_city=record.geo_city,
            geo_country=record.geo_country,
            ip=record.ip,
            user_agent=record.user_agent,
            created_at=record.created_at,
            expires_at=record.expires_at,
        )
        self._store(cancelled)
        self._append_audit(
            device_link_id=device_link_id,
            event="denied",
            ip=ip or record.ip,
            user_agent=user_agent or record.user_agent,
            user_id=user_id,
        )

    def cancel(self, device_link_id: str) -> None:
        record = self._get_record(device_link_id)
        if record.status in ("consumed", "cancelled", "expired"):
            return
        cancelled = DeviceLinkRecord(
            device_link_id=record.device_link_id,
            status="cancelled",
            code_challenge=record.code_challenge,
            confirmation_code=record.confirmation_code,
            redirect_hint=record.redirect_hint,
            browser=record.browser,
            os=record.os,
            geo_city=record.geo_city,
            geo_country=record.geo_country,
            ip=record.ip,
            user_agent=record.user_agent,
            created_at=record.created_at,
            expires_at=record.expires_at,
        )
        self._store(cancelled)
        self._append_audit(
            device_link_id=device_link_id,
            event="cancelled",
            ip=record.ip,
            user_agent=record.user_agent,
        )

    def poll_status(
        self,
        device_link_id: str,
        *,
        code_verifier: str,
        ip: str | None,
        user_agent: str | None,
    ) -> tuple[DeviceLinkRecord, BffUser | None]:
        record = self._get_record(device_link_id)
        if not verify_pkce(code_verifier, record.code_challenge):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid code verifier")
        if record.status == "expired":
            return record, None
        if record.status == "cancelled":
            return record, None
        if record.status == "consumed":
            return record, record.approved_user
        if record.status != "approved" or record.approved_user is None:
            return record, None
        session = bff_session_service.create_session(
            user=record.approved_user,
            access_token=record.access_token or "",
            refresh_token=record.refresh_token,
        )
        consumed = DeviceLinkRecord(
            device_link_id=record.device_link_id,
            status="consumed",
            code_challenge=record.code_challenge,
            confirmation_code=record.confirmation_code,
            redirect_hint=record.redirect_hint,
            browser=record.browser,
            os=record.os,
            geo_city=record.geo_city,
            geo_country=record.geo_country,
            ip=record.ip,
            user_agent=record.user_agent,
            created_at=record.created_at,
            expires_at=record.expires_at,
            approved_user=record.approved_user,
            approved_device_name=record.approved_device_name,
            machine_label=record.machine_label,
            session_id=session.session_id,
            access_token=record.access_token,
            refresh_token=record.refresh_token,
        )
        self._store(consumed)
        self._append_audit(
            device_link_id=device_link_id,
            event="poll_success",
            ip=ip,
            user_agent=user_agent,
            user_id=record.approved_user.sub,
        )
        bff_session_service.append_audit(
            event="poll_success",
            session_id=session.session_id,
            user_id=record.approved_user.sub,
            ip=ip,
            user_agent=user_agent,
        )
        return consumed, record.approved_user

    def list_audit(self) -> tuple[DeviceLinkAuditEntry, ...]:
        with self._lock:
            return tuple(self._audit)


device_link_service = DeviceLinkService()


def compute_machine_trust_key(
    *,
    user_id: str,
    ip: str | None,
    os_family: str,
    device_class: str,
) -> str:
    subnet = "unknown"
    if ip:
        try:
            addr = ipaddress.ip_address(ip)
            if isinstance(addr, ipaddress.IPv4Address):
                parts = ip.split(".")
                if len(parts) == 4:
                    subnet = f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
            else:
                subnet = str(addr)
        except ValueError:
            subnet = ip
    raw = f"{user_id}|{subnet}|{os_family}|{device_class}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

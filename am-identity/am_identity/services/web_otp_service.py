from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import HTTPException, status

from am_identity.email.web_otp_mailer import send_web_otp_email
from am_identity.services.bff_session_service import BffUser, bff_session_service
from am_identity.services.login_session_service import LoginContext, login_session_service

logger = logging.getLogger(__name__)

OtpChannel = Literal["email", "sms"]
OTP_TTL_SECONDS = 300
MAX_VERIFY_ATTEMPTS = 5
SEND_LIMIT = 3
SEND_WINDOW_SECONDS = 900

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[1-9]\d{9,14}$")


@dataclass(frozen=True, slots=True)
class OtpSession:
    otp_session_id: str
    channel: OtpChannel
    destination: str
    code: str
    user_id: str
    email: str | None
    created_at: float
    expires_at: float
    verify_attempts: int = 0
    consumed: bool = False


class WebOtpService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, OtpSession] = {}
        self._send_counts: dict[str, list[float]] = {}

    def _now(self) -> float:
        return time.time()

    def _normalize_destination(self, channel: OtpChannel, destination: str) -> str:
        cleaned = destination.strip()
        if channel == "email":
            if not _EMAIL.match(cleaned):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
            return cleaned.lower()
        digits = re.sub(r"[\s\-()]", "", cleaned)
        if not _PHONE.match(digits):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid phone number")
        return digits

    def _mask_destination(self, channel: OtpChannel, destination: str) -> str:
        if channel == "email":
            local, _, domain = destination.partition("@")
            if len(local) <= 2:
                masked_local = "*" * len(local)
            else:
                masked_local = f"{local[0]}***{local[-1]}"
            return f"{masked_local}@{domain}"
        if len(destination) <= 4:
            return "****"
        return f"{'*' * (len(destination) - 4)}{destination[-4:]}"

    def _check_send_rate(self, destination: str) -> None:
        now = self._now()
        cutoff = now - SEND_WINDOW_SECONDS
        key = destination
        with self._lock:
            hits = [ts for ts in self._send_counts.get(key, []) if ts >= cutoff]
            if len(hits) >= SEND_LIMIT:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many OTP requests. Please try again later.",
                )
            hits.append(now)
            self._send_counts[key] = hits

    async def send(
        self,
        *,
        channel: OtpChannel,
        destination: str,
        resolve_user_id,
    ) -> OtpSession:
        normalized = self._normalize_destination(channel, destination)
        self._check_send_rate(normalized)
        if channel == "sms":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SMS OTP is not available yet. Use email instead.",
            )
        user = await resolve_user_id(channel, normalized)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        now = self._now()
        code = f"{secrets.randbelow(1_000_000):06d}"
        session = OtpSession(
            otp_session_id=str(uuid.uuid4()),
            channel=channel,
            destination=normalized,
            code=code,
            user_id=user["id"],
            email=user.get("email"),
            created_at=now,
            expires_at=now + OTP_TTL_SECONDS,
        )
        with self._lock:
            self._sessions[session.otp_session_id] = session
        if channel == "email":
            send_web_otp_email(
                to_email=normalized,
                code=code,
                expires_minutes=max(1, OTP_TTL_SECONDS // 60),
            )
            logger.info("Web OTP email dispatched to %s", normalized)
        return session

    def pending_session(self, otp_session_id: str) -> OtpSession:
        with self._lock:
            session = self._sessions.get(otp_session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OTP session not found")
        if session.consumed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP already used")
        return session

    def verify(
        self,
        *,
        otp_session_id: str,
        code: str,
        ip: str | None,
        user_agent: str | None,
        access_token: str,
        refresh_token: str | None,
        machine_trust_key: str | None = None,
        geo_city: str | None = None,
        geo_country: str | None = None,
    ) -> tuple[BffUser, str]:
        with self._lock:
            session = self._sessions.get(otp_session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="OTP session not found")
        if session.consumed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OTP already used")
        if self._now() >= session.expires_at:
            raise HTTPException(status_code=status.HTTP_410_GONE, detail="OTP expired")
        attempts = session.verify_attempts + 1
        if not secrets.compare_digest(session.code, code.strip()):
            with self._lock:
                self._sessions[otp_session_id] = OtpSession(
                    otp_session_id=session.otp_session_id,
                    channel=session.channel,
                    destination=session.destination,
                    code=session.code,
                    user_id=session.user_id,
                    email=session.email,
                    created_at=session.created_at,
                    expires_at=session.expires_at,
                    verify_attempts=attempts,
                    consumed=False,
                )
            if attempts >= MAX_VERIFY_ATTEMPTS:
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP code")

        user = BffUser(
            sub=session.user_id,
            email=session.email,
            preferred_username=session.email,
        )
        bff = bff_session_service.create_session(
            user=user,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        login_session_service.record_login(
            LoginContext(
                user_id=session.user_id,
                email=session.email,
                client_type="web",
                browser=None,
                os=None,
                ip=ip,
                user_agent=user_agent,
                machine_trust_key=machine_trust_key,
                bff_session_id=bff.session_id,
                access_token=access_token,
                refresh_token=refresh_token,
                geo_city=geo_city,
                geo_country=geo_country,
            )
        )
        with self._lock:
            self._sessions[otp_session_id] = OtpSession(
                otp_session_id=session.otp_session_id,
                channel=session.channel,
                destination=session.destination,
                code=session.code,
                user_id=session.user_id,
                email=session.email,
                created_at=session.created_at,
                expires_at=session.expires_at,
                verify_attempts=attempts,
                consumed=True,
            )
        return user, bff.session_id

    def mask_destination(self, session: OtpSession) -> str:
        return self._mask_destination(session.channel, session.destination)


web_otp_service = WebOtpService()

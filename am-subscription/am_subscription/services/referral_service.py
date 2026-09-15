"""Referral invite codes, attribution, and qualify stubs (Phase 2 — no Pro grant)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from am_subscription.core.config import SubscriptionSettings
from am_subscription.models.db import (
    AttributionStatus,
    ReferralAttribution,
    ReferralCode,
    ReferralCodeStatus,
)

# Crockford-ish alphabet without 0/O/1/I (§19.4).
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_LIFETIME_CAP = 12
_DAILY_CAP = 3
_MIN_DEVICE_LEN = 16
_ACTIVE_STATUSES = (
    AttributionStatus.pending,
    AttributionStatus.qualified,
    AttributionStatus.rewarded,
)


def normalize_email(email: str | None) -> str | None:
    if not email or not email.strip():
        return None
    cleaned = email.strip().lower()
    local, _, domain = cleaned.partition("@")
    if not local or not domain:
        return cleaned
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+", 1)[0].replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def email_fingerprint(email: str | None) -> str | None:
    normalized = normalize_email(email)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_referral_code(code: str | None) -> str | None:
    if code is None:
        return None
    cleaned = code.strip().upper()
    return cleaned or None


def generate_invite_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))


class ReferralService:
    def __init__(self, session: AsyncSession, settings: SubscriptionSettings) -> None:
        self._session = session
        self._settings = settings
        self.lifetime_cap = _LIFETIME_CAP
        self.daily_cap = _DAILY_CAP

    def share_url_for(self, code: str) -> str:
        base = (self._settings.referral_share_base_url or "").rstrip("/")
        if not base:
            base = "https://asrax.in/download"
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}ref={code}"

    async def get_or_create_code(
        self, user_id: str, *, email: str | None = None
    ) -> ReferralCode:
        result = await self._session.execute(
            select(ReferralCode)
            .where(ReferralCode.user_id == user_id)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        fingerprint = email_fingerprint(email)
        if row is not None:
            if fingerprint and not row.owner_email_fingerprint:
                row.owner_email_fingerprint = fingerprint
                await self._session.commit()
                await self._session.refresh(row)
            return row

        for _ in range(12):
            code = generate_invite_code()
            exists = await self._session.execute(
                select(ReferralCode.id).where(ReferralCode.code == code)
            )
            if exists.scalar_one_or_none() is not None:
                continue
            row = ReferralCode(
                user_id=user_id,
                code=code,
                status=ReferralCodeStatus.active,
                qualified_count=0,
                owner_email_fingerprint=fingerprint,
            )
            self._session.add(row)
            await self._session.commit()
            await self._session.refresh(row)
            return row
        raise RuntimeError("Unable to allocate unique referral code")

    async def get_my_summary(
        self, user_id: str, *, email: str | None = None
    ) -> dict[str, Any]:
        code_row = await self.get_or_create_code(user_id, email=email)
        active = await self._count_active_for_referrer(user_id)
        remaining = max(0, self.lifetime_cap - active)
        daily_used = await self._count_daily_for_referrer(user_id)
        return {
            "code": code_row.code,
            "share_url": self.share_url_for(code_row.code),
            "status": code_row.status.value,
            "qualified_count": code_row.qualified_count,
            "active_count": active,
            "remaining": remaining,
            "lifetime_cap": self.lifetime_cap,
            "daily_used": daily_used,
            "daily_cap": self.daily_cap,
            "daily_remaining": max(0, self.daily_cap - daily_used),
            "joined": await self._joined_summary(user_id),
        }

    async def get_history(
        self, user_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Referrer view — date + status only (no invitee email / PII)."""
        result = await self._session.execute(
            select(ReferralAttribution)
            .where(ReferralAttribution.referrer_user_id == user_id)
            .order_by(ReferralAttribution.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        history: list[dict[str, Any]] = []
        for row in rows:
            history.append(
                {
                    "id": str(row.id),
                    "status": row.status.value,
                    "reject_reason": row.reject_reason,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "qualified_at": (
                        row.qualified_at.isoformat() if row.qualified_at else None
                    ),
                    # Masked code fragment only — never invitee email.
                    "code_hint": f"{row.code[:2]}******" if row.code else None,
                }
            )
        return history

    async def _joined_summary(self, user_id: str) -> dict[str, Any] | None:
        """Invite code this user joined with (referee view) — for first-run UI."""
        result = await self._session.execute(
            select(ReferralAttribution).where(
                ReferralAttribution.referee_user_id == user_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return {
            "code": row.code,
            "status": row.status.value,
            "reject_reason": row.reject_reason,
        }

    async def attribute(
        self,
        *,
        referee_user_id: str,
        email: str | None,
        referral_code: str | None,
        device_id: str | None,
        event_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ReferralAttribution | None:
        """
        Create pending/rejected attribution for a new user.
        Returns None when code/device missing or code unknown (no row).
        Idempotent by referee_user_id.
        """
        existing = await self._session.execute(
            select(ReferralAttribution).where(
                ReferralAttribution.referee_user_id == referee_user_id
            )
        )
        prior = existing.scalar_one_or_none()
        if prior is not None:
            return prior

        code = normalize_referral_code(referral_code)
        device = (device_id or "").strip() or None
        if not code or not device:
            return None
        if len(device) < _MIN_DEVICE_LEN:
            return None

        code_row = await self._lock_code_by_value(code)
        if code_row is None or code_row.status != ReferralCodeStatus.active:
            return None

        reject_reason = await self._evaluate_reject(
            code_row=code_row,
            referee_user_id=referee_user_id,
            email=email,
            device_id=device,
        )
        status = (
            AttributionStatus.rejected
            if reject_reason
            else AttributionStatus.pending
        )
        row = ReferralAttribution(
            referee_user_id=referee_user_id,
            referrer_user_id=code_row.user_id,
            code=code_row.code,
            device_id=device,
            status=status,
            reject_reason=reject_reason,
            referee_email_fingerprint=email_fingerprint(email),
            source_event_id=event_id,
            source_idempotency_key=idempotency_key,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def qualify(
        self, *, referee_user_id: str | None = None, attribution_id: UUID | None = None
    ) -> ReferralAttribution | None:
        """
        pending → qualified. Does not grant Pro or create rewards (Phase 3).
        """
        row = await self._load_attribution(
            referee_user_id=referee_user_id, attribution_id=attribution_id
        )
        if row is None:
            return None
        if row.status == AttributionStatus.qualified:
            return row
        if row.status == AttributionStatus.rewarded:
            return row
        if row.status != AttributionStatus.pending:
            return row

        code_row = await self._lock_code_by_user(row.referrer_user_id)
        if code_row is None:
            return row

        # Re-check caps at qualify (row lock on referrer code).
        reject = await self._evaluate_cap_only(code_row.user_id)
        if reject:
            row.status = AttributionStatus.rejected
            row.reject_reason = reject
            await self._session.commit()
            await self._session.refresh(row)
            return row

        row.status = AttributionStatus.qualified
        row.qualified_at = datetime.now(timezone.utc)
        row.reject_reason = None
        code_row.qualified_count = int(code_row.qualified_count or 0) + 1
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def upsert_pending_from_verify(
        self,
        *,
        referee_user_id: str,
        email: str | None,
        referral_code: str | None,
        device_id: str | None,
        event_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ReferralAttribution | None:
        """L8 helper for Phase 3 — attribute if missing, then qualify."""
        row = await self.attribute(
            referee_user_id=referee_user_id,
            email=email,
            referral_code=referral_code,
            device_id=device_id,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )
        if row is None:
            return None
        if row.status == AttributionStatus.pending:
            return await self.qualify(attribution_id=row.id)
        return row

    async def _load_attribution(
        self,
        *,
        referee_user_id: str | None,
        attribution_id: UUID | None,
    ) -> ReferralAttribution | None:
        if attribution_id is not None:
            result = await self._session.execute(
                select(ReferralAttribution)
                .where(ReferralAttribution.id == attribution_id)
                .with_for_update()
            )
            return result.scalar_one_or_none()
        if referee_user_id:
            result = await self._session.execute(
                select(ReferralAttribution)
                .where(ReferralAttribution.referee_user_id == referee_user_id)
                .with_for_update()
            )
            return result.scalar_one_or_none()
        return None

    async def _lock_code_by_value(self, code: str) -> ReferralCode | None:
        result = await self._session.execute(
            select(ReferralCode).where(ReferralCode.code == code).with_for_update()
        )
        return result.scalar_one_or_none()

    async def _lock_code_by_user(self, user_id: str) -> ReferralCode | None:
        result = await self._session.execute(
            select(ReferralCode)
            .where(ReferralCode.user_id == user_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def _evaluate_reject(
        self,
        *,
        code_row: ReferralCode,
        referee_user_id: str,
        email: str | None,
        device_id: str,
    ) -> str | None:
        if code_row.user_id == referee_user_id:
            return "self_referral"

        fingerprint = email_fingerprint(email)
        if (
            fingerprint
            and code_row.owner_email_fingerprint
            and fingerprint == code_row.owner_email_fingerprint
        ):
            return "same_email"

        if await self._device_already_used(device_id):
            return "device_already_used"

        if await self._device_used_by_user(device_id, code_row.user_id):
            return "device_already_used"

        return await self._evaluate_cap_only(code_row.user_id)

    async def _evaluate_cap_only(self, referrer_user_id: str) -> str | None:
        if await self._count_active_for_referrer(referrer_user_id) >= self.lifetime_cap:
            return "lifetime_cap"
        if await self._count_daily_for_referrer(referrer_user_id) >= self.daily_cap:
            return "daily_cap"
        return None

    def _active_filter(self, referrer_user_id: str) -> Select[Any]:
        return select(func.count()).select_from(ReferralAttribution).where(
            ReferralAttribution.referrer_user_id == referrer_user_id,
            ReferralAttribution.status.in_(_ACTIVE_STATUSES),
        )

    async def _count_active_for_referrer(self, referrer_user_id: str) -> int:
        result = await self._session.execute(self._active_filter(referrer_user_id))
        return int(result.scalar_one() or 0)

    async def _count_daily_for_referrer(self, referrer_user_id: str) -> int:
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        result = await self._session.execute(
            select(func.count())
            .select_from(ReferralAttribution)
            .where(
                ReferralAttribution.referrer_user_id == referrer_user_id,
                ReferralAttribution.status.in_(_ACTIVE_STATUSES),
                ReferralAttribution.created_at >= start,
            )
        )
        return int(result.scalar_one() or 0)

    async def _device_already_used(self, device_id: str) -> bool:
        result = await self._session.execute(
            select(ReferralAttribution.id).where(
                ReferralAttribution.device_id == device_id,
                ReferralAttribution.status.in_(_ACTIVE_STATUSES),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _device_used_by_user(self, device_id: str, user_id: str) -> bool:
        """Reject if device was ever used where user was referrer or referee."""
        result = await self._session.execute(
            select(ReferralAttribution.id)
            .where(
                ReferralAttribution.device_id == device_id,
                or_(
                    ReferralAttribution.referrer_user_id == user_id,
                    ReferralAttribution.referee_user_id == user_id,
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

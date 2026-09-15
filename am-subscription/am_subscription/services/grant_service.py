"""Unified timed Pro grants, delayed schedules, and expiry (Phase 3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from am_subscription.core.config import SubscriptionSettings
from am_subscription.core.log_utils import get_logger
from am_subscription.models.db import (
    AttributionStatus,
    GrantSchedule,
    GrantScheduleKind,
    GrantScheduleStatus,
    ReferralAttribution,
    ReferralReward,
    Subscription,
    SubscriptionAudit,
    SubscriptionState,
)
from am_subscription.providers.lago_provider import LagoProvider
from am_subscription.schemas.subscription import CreateSubscriptionRequest
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.referral_service import ReferralService, email_fingerprint
from am_subscription.services.subscription_service import SubscriptionService

logger = get_logger("grant_service")

TRIAL_HOURS = 30 * 24  # 720
REFERRAL_DAYS = 14
PRO_PLAN = "am_pro"
FREE_PLAN = "am_free"


class GrantService:
    def __init__(
        self,
        session: AsyncSession,
        settings: SubscriptionSettings,
        subscription_service: SubscriptionService,
        referral_service: ReferralService,
        provider: LagoProvider,
        events: EventPublisher,
    ) -> None:
        self._session = session
        self._settings = settings
        self._subs = subscription_service
        self._referrals = referral_service
        self._provider = provider
        self._events = events

    def _trial_delay(self) -> timedelta:
        return timedelta(hours=float(self._settings.trial_grant_delay_hours))

    def _referral_delay(self) -> timedelta:
        return timedelta(hours=float(self._settings.referral_reward_delay_hours))

    @staticmethod
    def effective_pro_end(sub: Subscription) -> datetime | None:
        ends = [t for t in (sub.trial_pro_expires_at, sub.referral_pro_expires_at) if t]
        if not ends:
            return None

        def _aware(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt

        return max(_aware(t) for t in ends)

    async def ensure_subscription_row(
        self, user_id: str, *, email: str | None = None
    ) -> Subscription:
        existing = await self._subs.get_by_user(user_id)
        if existing:
            if email:
                await self._subs.sync_lago_customer_email(user_id, email)
            return existing
        await self._subs.get_or_create(
            user_id,
            CreateSubscriptionRequest(plan_code=FREE_PLAN),
            actor="system:grant",
            correlation_id=EventPublisher.new_correlation_id(),
            email=email,
        )
        row = await self._subs.get_by_user(user_id)
        assert row is not None
        return row

    async def schedule_or_run(
        self,
        *,
        user_id: str,
        kind: GrantScheduleKind,
        idempotency_key: str,
        payload: dict[str, Any],
        delay: timedelta,
    ) -> GrantSchedule:
        existing = await self._session.execute(
            select(GrantSchedule).where(GrantSchedule.idempotency_key == idempotency_key)
        )
        prior = existing.scalar_one_or_none()
        if prior is not None:
            return prior

        now = datetime.now(timezone.utc)
        execute_at = now + delay
        row = GrantSchedule(
            user_id=user_id,
            kind=kind,
            payload_json=payload,
            execute_at=execute_at,
            status=GrantScheduleStatus.pending,
            idempotency_key=idempotency_key,
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)

        if delay <= timedelta(0):
            await self.execute_schedule(row.id)
            await self._session.refresh(row)
        else:
            if kind == GrantScheduleKind.trial:
                await self._events.publish(
                    "am.subscription.trial_scheduled.v1",
                    tenant_id=user_id,
                    user_id=user_id,
                    correlation_id=EventPublisher.new_correlation_id(),
                    idempotency_key=f"trial-scheduled:{user_id}",
                    payload={
                        "user_id": user_id,
                        "execute_at": execute_at.isoformat(),
                    },
                )
        return row

    async def grant_pro_days(
        self,
        *,
        user_id: str,
        days: int,
        plan_code: str = PRO_PLAN,
        reason: str,
        idempotency_key: str,
        email: str | None = None,
        attribution_id: str | None = None,
        execute_at: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Unified timed Pro grant.
        reason=trial → 30×24h once per email fingerprint
        reason=referral → stack +14×24h on referral_pro_expires_at
        """
        now = execute_at or datetime.now(timezone.utc)
        sub = await self.ensure_subscription_row(user_id, email=email)

        if reason == "trial":
            return await self._grant_trial(
                sub,
                user_id=user_id,
                days=days,
                plan_code=plan_code,
                idempotency_key=idempotency_key,
                email=email,
                now=now,
            )
        if reason == "referral":
            return await self._grant_referral(
                sub,
                user_id=user_id,
                days=days,
                plan_code=plan_code,
                idempotency_key=idempotency_key,
                attribution_id=attribution_id,
                now=now,
            )
        raise ValueError(f"Unsupported grant reason: {reason}")

    async def _grant_trial(
        self,
        sub: Subscription,
        *,
        user_id: str,
        days: int,
        plan_code: str,
        idempotency_key: str,
        email: str | None,
        now: datetime,
    ) -> dict[str, Any]:
        # Already granted trial for this user
        if sub.trial_pro_expires_at is not None:
            return {
                "status": "idempotent",
                "user_id": user_id,
                "reason": "trial",
                "trial_pro_expires_at": sub.trial_pro_expires_at.isoformat(),
            }

        fingerprint = email_fingerprint(email)
        if fingerprint:
            clash = await self._session.execute(
                select(Subscription).where(
                    Subscription.trial_email_fingerprint == fingerprint,
                    Subscription.user_id != user_id,
                )
            )
            if clash.scalar_one_or_none() is not None:
                return {
                    "status": "blocked",
                    "reason": "trial_email_used",
                    "user_id": user_id,
                }

        hours = days * 24 if days else TRIAL_HOURS
        # Prefer exact 720h for standard trial
        if days == 30:
            hours = TRIAL_HOURS
        expires = now + timedelta(hours=hours)

        paid_sticky = bool(sub.is_paid)
        if not paid_sticky:
            await self._apply_pro_plan(sub, plan_code=plan_code)
            if sub.grant_source != "paid":
                sub.grant_source = "trial"

        sub.trial_starts_at = now
        sub.trial_pro_expires_at = expires
        if fingerprint:
            sub.trial_email_fingerprint = fingerprint
        sub.updated_at = now

        await self._audit(
            sub.id,
            actor="system:trial",
            reason="trial_grant",
            correlation_id=idempotency_key,
            metadata={
                "idempotency_key": idempotency_key,
                "expires_at": expires.isoformat(),
                "paid_sticky": paid_sticky,
            },
        )
        await self._session.commit()
        await self._session.refresh(sub)

        await self._events.publish(
            "am.subscription.trial_started.v1",
            tenant_id=sub.tenant_id or user_id,
            user_id=user_id,
            correlation_id=EventPublisher.new_correlation_id(),
            idempotency_key=idempotency_key,
            payload={
                "user_id": user_id,
                "trial_pro_expires_at": expires.isoformat(),
                "paid_sticky": paid_sticky,
            },
        )
        return {
            "status": "granted",
            "user_id": user_id,
            "reason": "trial",
            "trial_pro_expires_at": expires.isoformat(),
            "paid_sticky": paid_sticky,
            "plan_code": sub.plan_code,
        }

    async def _grant_referral(
        self,
        sub: Subscription,
        *,
        user_id: str,
        days: int,
        plan_code: str,
        idempotency_key: str,
        attribution_id: str | None,
        now: datetime,
    ) -> dict[str, Any]:
        # Idempotent reward row
        existing_reward = await self._session.execute(
            select(ReferralReward).where(
                ReferralReward.idempotency_key == idempotency_key
            )
        )
        prior_reward = existing_reward.scalar_one_or_none()
        if prior_reward is not None:
            return {
                "status": "idempotent",
                "user_id": user_id,
                "reason": "referral",
                "idempotency_key": idempotency_key,
            }

        attr_uuid: UUID | None = None
        attribution: ReferralAttribution | None = None
        if attribution_id:
            attr_uuid = UUID(str(attribution_id))
            attribution = await self._referrals.qualify(attribution_id=attr_uuid)
            if attribution and attribution.status == AttributionStatus.rejected:
                return {
                    "status": "blocked",
                    "reason": attribution.reject_reason or "rejected",
                    "user_id": user_id,
                }

        delta = timedelta(days=days or REFERRAL_DAYS)
        base = sub.referral_pro_expires_at
        if base is None or base < now:
            base = now
        new_expiry = base + delta

        paid_sticky = bool(sub.is_paid)
        if not paid_sticky:
            await self._apply_pro_plan(sub, plan_code=plan_code)
            if sub.grant_source != "paid":
                sub.grant_source = "referral"

        # Bank days even when paid (L15)
        sub.referral_pro_expires_at = new_expiry
        sub.updated_at = now

        if attribution is not None and attr_uuid is not None:
            attribution.status = AttributionStatus.rewarded
            reward = ReferralReward(
                attribution_id=attr_uuid,
                beneficiary_user_id=user_id,
                reward_type="pro_days",
                days=days or REFERRAL_DAYS,
                plan_code=plan_code,
                idempotency_key=idempotency_key,
                granted_at=now,
                expires_at=new_expiry,
            )
            self._session.add(reward)

        await self._audit(
            sub.id,
            actor="system:referral",
            reason="referral_grant",
            correlation_id=idempotency_key,
            metadata={
                "idempotency_key": idempotency_key,
                "expires_at": new_expiry.isoformat(),
                "paid_sticky": paid_sticky,
                "attribution_id": attribution_id,
            },
        )
        await self._session.commit()
        await self._session.refresh(sub)

        await self._events.publish(
            "am.referral.rewarded.v1",
            tenant_id=sub.tenant_id or user_id,
            user_id=user_id,
            correlation_id=EventPublisher.new_correlation_id(),
            idempotency_key=idempotency_key,
            payload={
                "user_id": user_id,
                "referral_pro_expires_at": new_expiry.isoformat(),
                "attribution_id": attribution_id,
                "paid_sticky": paid_sticky,
            },
        )
        return {
            "status": "granted",
            "user_id": user_id,
            "reason": "referral",
            "referral_pro_expires_at": new_expiry.isoformat(),
            "paid_sticky": paid_sticky,
            "plan_code": sub.plan_code,
        }

    async def _apply_pro_plan(self, sub: Subscription, *, plan_code: str) -> None:
        if sub.plan_code == plan_code:
            return
        previous = sub.plan_code
        if sub.provider_subscription_id:
            try:
                await self._provider.change_plan(
                    sub.provider_subscription_id, plan_code
                )
            except Exception:
                logger.exception(
                    "lago_change_plan_failed user_id=%s plan=%s",
                    sub.user_id,
                    plan_code,
                )
        sub.plan_code = plan_code
        if sub.state in (SubscriptionState.cancelled, SubscriptionState.expired):
            sub.state = SubscriptionState.active
        logger.info(
            "local_plan_set",
            extra={
                "user_id": sub.user_id,
                "previous_plan": previous,
                "plan_code": plan_code,
            },
        )

    async def _apply_free_plan(self, sub: Subscription) -> None:
        if sub.plan_code == FREE_PLAN:
            return
        if sub.provider_subscription_id:
            try:
                await self._provider.change_plan(
                    sub.provider_subscription_id, FREE_PLAN
                )
            except Exception:
                logger.exception(
                    "lago_downgrade_failed user_id=%s", sub.user_id
                )
        sub.plan_code = FREE_PLAN
        if sub.grant_source in ("trial", "referral", "bootstrap", None):
            sub.grant_source = "bootstrap"

    async def handle_email_verified(
        self,
        *,
        user_id: str,
        email: str | None,
        referral_code: str | None,
        device_id: str | None,
        event_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """L8: upsert attribution, schedule trial (+ referral reward if attributed)."""
        await self._subs.sync_lago_customer_email(user_id, email)

        attribution = await self._referrals.upsert_pending_from_verify(
            referee_user_id=user_id,
            email=email,
            referral_code=referral_code,
            device_id=device_id,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )

        trial_key = f"trial:{user_id}"
        trial_sched = await self.schedule_or_run(
            user_id=user_id,
            kind=GrantScheduleKind.trial,
            idempotency_key=trial_key,
            payload={"email": email, "days": 30, "plan_code": PRO_PLAN},
            delay=self._trial_delay(),
        )

        reward_sched = None
        if (
            attribution is not None
            and attribution.status
            in (AttributionStatus.pending, AttributionStatus.qualified)
        ):
            reward_key = f"ref-reward:{attribution.id}:referrer"
            reward_sched = await self.schedule_or_run(
                user_id=attribution.referrer_user_id,
                kind=GrantScheduleKind.referral_reward,
                idempotency_key=reward_key,
                payload={
                    "attribution_id": str(attribution.id),
                    "days": REFERRAL_DAYS,
                    "plan_code": PRO_PLAN,
                },
                delay=self._referral_delay(),
            )
            if attribution.status == AttributionStatus.qualified:
                await self._events.publish(
                    "am.referral.qualified.v1",
                    tenant_id=attribution.referrer_user_id,
                    user_id=attribution.referrer_user_id,
                    correlation_id=EventPublisher.new_correlation_id(),
                    idempotency_key=f"ref-qualified:{attribution.id}",
                    payload={
                        "attribution_id": str(attribution.id),
                        "referrer_user_id": attribution.referrer_user_id,
                        "referee_user_id": attribution.referee_user_id,
                    },
                )

        return {
            "trial_schedule_id": str(trial_sched.id),
            "trial_status": trial_sched.status.value,
            "reward_schedule_id": str(reward_sched.id) if reward_sched else None,
            "attribution_status": attribution.status.value if attribution else None,
        }

    async def execute_schedule(self, schedule_id: UUID) -> GrantSchedule | None:
        result = await self._session.execute(
            select(GrantSchedule)
            .where(GrantSchedule.id == schedule_id)
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None or row.status != GrantScheduleStatus.pending:
            return row

        payload = row.payload_json or {}
        try:
            if row.kind == GrantScheduleKind.trial:
                await self.grant_pro_days(
                    user_id=row.user_id,
                    days=int(payload.get("days") or 30),
                    plan_code=str(payload.get("plan_code") or PRO_PLAN),
                    reason="trial",
                    idempotency_key=row.idempotency_key,
                    email=payload.get("email"),
                    execute_at=datetime.now(timezone.utc),
                )
            elif row.kind == GrantScheduleKind.referral_reward:
                await self.grant_pro_days(
                    user_id=row.user_id,
                    days=int(payload.get("days") or REFERRAL_DAYS),
                    plan_code=str(payload.get("plan_code") or PRO_PLAN),
                    reason="referral",
                    idempotency_key=row.idempotency_key,
                    attribution_id=payload.get("attribution_id"),
                    execute_at=datetime.now(timezone.utc),
                )
            row.status = GrantScheduleStatus.done
            row.completed_at = datetime.now(timezone.utc)
            row.error_message = None
        except Exception as exc:
            logger.exception("grant_schedule_failed id=%s", schedule_id)
            row.error_message = str(exc)[:500]
            # leave pending for retry
        await self._session.commit()
        await self._session.refresh(row)
        return row

    async def process_due_schedules(self, *, limit: int = 50) -> int:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(GrantSchedule)
            .where(
                GrantSchedule.status == GrantScheduleStatus.pending,
                GrantSchedule.execute_at <= now,
            )
            .order_by(GrantSchedule.execute_at.asc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        done = 0
        for row in rows:
            updated = await self.execute_schedule(row.id)
            if updated and updated.status == GrantScheduleStatus.done:
                done += 1
        return done

    async def process_expiries(self, *, limit: int = 100) -> int:
        """Revert free/trial users whose timed Pro window ended. Skip is_paid."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(Subscription)
            .where(Subscription.is_paid.is_(False))
            .limit(limit)
        )
        changed = 0
        for sub in result.scalars().all():
            if sub.plan_code != PRO_PLAN:
                continue
            end = self.effective_pro_end(sub)
            if end is None or end > now:
                continue
            await self._apply_free_plan(sub)
            sub.updated_at = now
            await self._audit(
                sub.id,
                actor="system:expiry",
                reason="timed_pro_expired",
                correlation_id=f"expiry:{sub.user_id}:{int(now.timestamp())}",
                metadata={"effective_end": end.isoformat()},
            )
            changed += 1
        if changed:
            await self._session.commit()
        return changed

    async def mark_paid(self, user_id: str, *, is_paid: bool = True) -> Subscription:
        sub = await self.ensure_subscription_row(user_id)
        sub.is_paid = is_paid
        if is_paid:
            sub.grant_source = "paid"
        sub.updated_at = datetime.now(timezone.utc)
        await self._session.commit()
        await self._session.refresh(sub)
        return sub

    async def apply_after_paid_cancel(self, sub: Subscription) -> Subscription:
        """L15 — after paid cancel, keep Pro if banked referral days remain."""
        now = datetime.now(timezone.utc)
        sub.is_paid = False
        end = self.effective_pro_end(sub)
        if end and end > now:
            await self._apply_pro_plan(sub, plan_code=PRO_PLAN)
            if sub.grant_source == "paid":
                sub.grant_source = "referral"
            if sub.state == SubscriptionState.cancelled:
                sub.state = SubscriptionState.active
        else:
            await self._apply_free_plan(sub)
        sub.updated_at = now
        await self._session.commit()
        await self._session.refresh(sub)
        return sub

    async def _audit(
        self,
        subscription_id: UUID,
        *,
        actor: str,
        reason: str,
        correlation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            SubscriptionAudit(
                subscription_id=subscription_id,
                actor=actor,
                reason=reason,
                previous_state=None,
                next_state="grant",
                correlation_id=correlation_id,
                metadata_json=metadata,
            )
        )

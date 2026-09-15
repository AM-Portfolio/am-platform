"""Phase 3 timed Pro grants, schedules, fingerprint, paid sticky."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from am_subscription.core.config import SubscriptionSettings
from am_subscription.core.database import Base
from am_subscription.core.plan_catalog import get_plan_catalog
from am_subscription.models.db import (
    AttributionStatus,
    GrantSchedule,
    GrantScheduleKind,
    GrantScheduleStatus,
    MeterBuffer,
    ReferralAttribution,
    ReferralCode,
    ReferralReward,
    Subscription,
    SubscriptionAudit,
    SubscriptionState,
)
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.grant_service import TRIAL_HOURS, GrantService
from am_subscription.services.referral_service import ReferralService
from am_subscription.services.subscription_service import SubscriptionService


class FakeLago:
    async def ensure_customer(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"external_id": args[0] if args else "cust"}

    async def create_subscription(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"external_id": kwargs.get("external_id") or "sub"}

    async def change_plan(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"plan_code": args[1] if len(args) > 1 else "am_pro"}

    async def cancel_subscription(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}


def _settings(**overrides: Any) -> SubscriptionSettings:
    base = {
        "REFERRAL_SHARE_BASE_URL": "https://asrax.in/download",
        "APP_ENV": "test",
        "AM_SUBSCRIPTION_DB_PASSWORD": "",
        "TRIAL_GRANT_DELAY_HOURS": "0",
        "REFERRAL_REWARD_DELAY_HOURS": "0",
        "GRANT_POLLER_ENABLED": "false",
        "DEFAULT_PLAN_CODE": "am_free",
    }
    base.update(overrides)
    return SubscriptionSettings(**base)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        Subscription.__table__,
        SubscriptionAudit.__table__,
        MeterBuffer.__table__,
        ReferralCode.__table__,
        ReferralAttribution.__table__,
        ReferralReward.__table__,
        GrantSchedule.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


async def _seed_sub(
    session: AsyncSession,
    user_id: str,
    *,
    plan_code: str = "am_free",
    is_paid: bool = False,
) -> Subscription:
    row = Subscription(
        user_id=user_id,
        plan_code=plan_code,
        state=SubscriptionState.active,
        provider="lago",
        provider_subscription_id=f"sub-{user_id}",
        billing_interval="monthly",
        is_paid=is_paid,
        grant_source="paid" if is_paid else "bootstrap",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


def _services(session: AsyncSession, settings: SubscriptionSettings | None = None):
    settings = settings or _settings()
    catalog = get_plan_catalog()
    provider = FakeLago()
    events = EventPublisher(settings)
    subs = SubscriptionService(
        session, catalog, provider, events, settings.default_plan_code
    )
    referrals = ReferralService(session, settings)
    grants = GrantService(session, settings, subs, referrals, provider, events)
    return grants, referrals, subs


@pytest.mark.asyncio
async def test_trial_duration_is_720_hours(session: AsyncSession) -> None:
    await _seed_sub(session, "u-trial")
    grants, _, _ = _services(session)
    before = datetime.now(timezone.utc)
    result = await grants.grant_pro_days(
        user_id="u-trial",
        days=30,
        reason="trial",
        idempotency_key="trial:u-trial",
        email="new@example.com",
    )
    assert result["status"] == "granted"
    sub = await grants._subs.get_by_user("u-trial")
    assert sub is not None
    assert sub.trial_pro_expires_at is not None
    delta = sub.trial_pro_expires_at - (sub.trial_starts_at or before)
    assert abs(delta.total_seconds() - TRIAL_HOURS * 3600) < 5
    assert sub.plan_code == "am_pro"


@pytest.mark.asyncio
async def test_delay_schedule_then_poller_applies(session: AsyncSession) -> None:
    await _seed_sub(session, "u-delay")
    settings = _settings(TRIAL_GRANT_DELAY_HOURS="24")
    grants, _, _ = _services(session, settings)
    sched = await grants.schedule_or_run(
        user_id="u-delay",
        kind=GrantScheduleKind.trial,
        idempotency_key="trial:u-delay",
        payload={"email": "d@example.com", "days": 30, "plan_code": "am_pro"},
        delay=timedelta(hours=24),
    )
    assert sched.status == GrantScheduleStatus.pending
    sub = await grants._subs.get_by_user("u-delay")
    assert sub is not None
    assert sub.trial_pro_expires_at is None

    # Make due and run poller tick logic
    sched.execute_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await session.commit()
    done = await grants.process_due_schedules()
    assert done == 1
    await session.refresh(sub)
    assert sub.trial_pro_expires_at is not None
    assert sub.plan_code == "am_pro"


@pytest.mark.asyncio
async def test_same_email_fingerprint_blocks_second_trial(
    session: AsyncSession,
) -> None:
    await _seed_sub(session, "u-a")
    await _seed_sub(session, "u-b")
    grants, _, _ = _services(session)
    first = await grants.grant_pro_days(
        user_id="u-a",
        days=30,
        reason="trial",
        idempotency_key="trial:u-a",
        email="Same.Person+one@gmail.com",
    )
    second = await grants.grant_pro_days(
        user_id="u-b",
        days=30,
        reason="trial",
        idempotency_key="trial:u-b",
        email="sameperson@googlemail.com",
    )
    assert first["status"] == "granted"
    assert second["status"] == "blocked"
    assert second["reason"] == "trial_email_used"


@pytest.mark.asyncio
async def test_out_of_order_verify_upserts_pending(session: AsyncSession) -> None:
    await _seed_sub(session, "referee-oo")
    await _seed_sub(session, "referrer-oo")
    settings = _settings()
    grants, referrals, _ = _services(session, settings)
    code = await referrals.get_or_create_code("referrer-oo", email="ref@example.com")
    # No user_registered attribute yet — verify carries code (L8)
    result = await grants.handle_email_verified(
        user_id="referee-oo",
        email="new@example.com",
        referral_code=code.code,
        device_id="device-outoforder001",
        idempotency_key="email-verified:referee-oo",
    )
    assert result["attribution_status"] in ("qualified", "rewarded")
    assert result["reward_schedule_id"] is not None
    from sqlalchemy import select

    row = (
        await session.execute(
            select(ReferralAttribution).where(
                ReferralAttribution.referee_user_id == "referee-oo"
            )
        )
    ).scalar_one()
    await session.refresh(row)
    # delay=0 → reward executed → rewarded
    assert row.status == AttributionStatus.rewarded


@pytest.mark.asyncio
async def test_paid_sticky_banks_referral_days(session: AsyncSession) -> None:
    await _seed_sub(session, "paid-user", plan_code="am_pro", is_paid=True)
    grants, referrals, _ = _services(session)
    code = await referrals.get_or_create_code("paid-user", email="paid@example.com")
    await _seed_sub(session, "invitee-1")
    attr = await referrals.attribute(
        referee_user_id="invitee-1",
        email="inv@example.com",
        referral_code=code.code,
        device_id="device-paid-bank-0001",
    )
    assert attr is not None
    await referrals.qualify(attribution_id=attr.id)
    result = await grants.grant_pro_days(
        user_id="paid-user",
        days=14,
        reason="referral",
        idempotency_key=f"ref-reward:{attr.id}:referrer",
        attribution_id=str(attr.id),
    )
    assert result["status"] == "granted"
    assert result["paid_sticky"] is True
    sub = await grants._subs.get_by_user("paid-user")
    assert sub is not None
    assert sub.is_paid is True
    assert sub.referral_pro_expires_at is not None
    assert sub.plan_code == "am_pro"

    # Cancel paid → banked Pro remains
    dto = await grants._subs.cancel(
        sub.id,
        "paid-user",
        actor="user",
        reason="cancel",
        correlation_id="c1",
    )
    assert dto.plan_code == "am_pro"
    assert dto.is_paid is False
    assert dto.state == SubscriptionState.active


@pytest.mark.asyncio
async def test_internal_grant_route_requires_service_account() -> None:
    from am_subscription.api import internal_router

    route = next(
        r
        for r in internal_router.router.routes
        if getattr(r, "path", "") == "/subscriptions/internal/grants/pro-days"
    )
    # FastAPI stores dependencies; require_service_account must be present
    dep_names = []
    for dep in route.dependant.dependencies:
        call = getattr(dep, "call", None)
        dep_names.append(getattr(call, "__name__", str(call)))
    assert any("service" in n.lower() or "auth" in n.lower() for n in dep_names)


@pytest.mark.asyncio
async def test_idempotent_trial_grant(session: AsyncSession) -> None:
    await _seed_sub(session, "u-idem")
    grants, _, _ = _services(session)
    a = await grants.grant_pro_days(
        user_id="u-idem",
        days=30,
        reason="trial",
        idempotency_key="trial:u-idem",
        email="idem@example.com",
    )
    b = await grants.grant_pro_days(
        user_id="u-idem",
        days=30,
        reason="trial",
        idempotency_key="trial:u-idem",
        email="idem@example.com",
    )
    assert a["status"] == "granted"
    assert b["status"] == "idempotent"


@pytest.mark.asyncio
async def test_expiry_reverts_non_paid(session: AsyncSession) -> None:
    sub = await _seed_sub(session, "u-exp", plan_code="am_pro")
    sub.trial_pro_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    sub.is_paid = False
    await session.commit()
    grants, _, _ = _services(session)
    n = await grants.process_expiries()
    assert n == 1
    await session.refresh(sub)
    assert sub.plan_code == "am_free"

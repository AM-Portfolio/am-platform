"""Phase 2 referral ledger — attribute / qualify / caps (no Pro grant)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from am_subscription.core.config import SubscriptionSettings
from am_subscription.core.database import Base
from am_subscription.models.db import (
    AttributionStatus,
    ReferralAttribution,
    ReferralCode,
    ReferralReward,
)
from am_subscription.services.referral_service import (
    ReferralService,
    email_fingerprint,
    normalize_email,
)


def _settings() -> SubscriptionSettings:
    return SubscriptionSettings(
        REFERRAL_SHARE_BASE_URL="https://asrax.in/download",
        APP_ENV="test",
        AM_SUBSCRIPTION_DB_PASSWORD="",
    )


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        ReferralCode.__table__,
        ReferralAttribution.__table__,
        ReferralReward.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def service(session: AsyncSession) -> ReferralService:
    return ReferralService(session, _settings())


@pytest.mark.asyncio
async def test_valid_code_becomes_pending(service: ReferralService) -> None:
    referrer = await service.get_or_create_code("referrer-1", email="ref@example.com")
    row = await service.attribute(
        referee_user_id="referee-1",
        email="new@example.com",
        referral_code=referrer.code,
        device_id="device-aaaaaaaaaaaa",
    )
    assert row is not None
    assert row.status == AttributionStatus.pending
    assert row.reject_reason is None
    assert row.referrer_user_id == "referrer-1"


@pytest.mark.asyncio
async def test_self_referral_rejected(service: ReferralService) -> None:
    code = await service.get_or_create_code("user-1", email="a@example.com")
    row = await service.attribute(
        referee_user_id="user-1",
        email="a+alt@example.com",
        referral_code=code.code,
        device_id="device-bbbbbbbbbbbb",
    )
    assert row is not None
    assert row.status == AttributionStatus.rejected
    assert row.reject_reason == "self_referral"


@pytest.mark.asyncio
async def test_same_email_rejected(service: ReferralService) -> None:
    code = await service.get_or_create_code(
        "referrer-2", email="same.person@gmail.com"
    )
    row = await service.attribute(
        referee_user_id="referee-2",
        email="sameperson+tag@gmail.com",
        referral_code=code.code,
        device_id="device-cccccccccccc",
    )
    assert row is not None
    assert row.status == AttributionStatus.rejected
    assert row.reject_reason == "same_email"


@pytest.mark.asyncio
async def test_device_already_used_rejected(service: ReferralService) -> None:
    code = await service.get_or_create_code("referrer-3", email="r3@example.com")
    first = await service.attribute(
        referee_user_id="referee-3a",
        email="a@example.com",
        referral_code=code.code,
        device_id="device-dddddddddddd",
    )
    assert first is not None
    assert first.status == AttributionStatus.pending

    other = await service.get_or_create_code("referrer-3b", email="r3b@example.com")
    second = await service.attribute(
        referee_user_id="referee-3b",
        email="b@example.com",
        referral_code=other.code,
        device_id="device-dddddddddddd",
    )
    assert second is not None
    assert second.status == AttributionStatus.rejected
    assert second.reject_reason == "device_already_used"


@pytest.mark.asyncio
async def test_missing_device_id_no_attribution(service: ReferralService) -> None:
    code = await service.get_or_create_code("referrer-4", email="r4@example.com")
    row = await service.attribute(
        referee_user_id="referee-4",
        email="n@example.com",
        referral_code=code.code,
        device_id=None,
    )
    assert row is None

    short = await service.attribute(
        referee_user_id="referee-4b",
        email="n2@example.com",
        referral_code=code.code,
        device_id="short",
    )
    assert short is None


@pytest.mark.asyncio
async def test_lifetime_cap_12(service: ReferralService) -> None:
    service.lifetime_cap = 2
    code = await service.get_or_create_code("referrer-cap", email="cap@example.com")
    for i in range(2):
        row = await service.attribute(
            referee_user_id=f"cap-ref-{i}",
            email=f"cap{i}@example.com",
            referral_code=code.code,
            device_id=f"device-cap-{i:012d}",
        )
        assert row is not None
        assert row.status == AttributionStatus.pending

    blocked = await service.attribute(
        referee_user_id="cap-ref-overflow",
        email="overflow@example.com",
        referral_code=code.code,
        device_id="device-cap-overflow1",
    )
    assert blocked is not None
    assert blocked.status == AttributionStatus.rejected
    assert blocked.reject_reason == "lifetime_cap"


@pytest.mark.asyncio
async def test_daily_cap_3(service: ReferralService) -> None:
    service.daily_cap = 1
    service.lifetime_cap = 12
    code = await service.get_or_create_code("referrer-day", email="day@example.com")
    first = await service.attribute(
        referee_user_id="day-1",
        email="d1@example.com",
        referral_code=code.code,
        device_id="device-day-00000001",
    )
    assert first is not None
    assert first.status == AttributionStatus.pending

    second = await service.attribute(
        referee_user_id="day-2",
        email="d2@example.com",
        referral_code=code.code,
        device_id="device-day-00000002",
    )
    assert second is not None
    assert second.status == AttributionStatus.rejected
    assert second.reject_reason == "daily_cap"


@pytest.mark.asyncio
async def test_history_has_no_pii_emails(service: ReferralService) -> None:
    code = await service.get_or_create_code("referrer-hist", email="hist@example.com")
    await service.attribute(
        referee_user_id="hist-ref",
        email="secret.invitee@example.com",
        referral_code=code.code,
        device_id="device-hist-0000001",
    )
    history = await service.get_history("referrer-hist")
    assert len(history) == 1
    blob = str(history)
    assert "secret.invitee" not in blob
    assert "email" not in history[0]
    assert history[0]["status"] == "pending"
    assert history[0]["code_hint"] is not None


@pytest.mark.asyncio
async def test_share_url_and_stable_code(service: ReferralService) -> None:
    first = await service.get_my_summary("stable-user", email="s@example.com")
    second = await service.get_my_summary("stable-user", email="s@example.com")
    assert first["code"] == second["code"]
    assert first["share_url"] == f"https://asrax.in/download?ref={first['code']}"
    assert len(first["code"]) == 8


@pytest.mark.asyncio
async def test_qualify_pending_to_qualified(service: ReferralService) -> None:
    code = await service.get_or_create_code("referrer-q", email="q@example.com")
    row = await service.attribute(
        referee_user_id="referee-q",
        email="nq@example.com",
        referral_code=code.code,
        device_id="device-qualify-0001",
    )
    assert row is not None
    qualified = await service.qualify(attribution_id=row.id)
    assert qualified is not None
    assert qualified.status == AttributionStatus.qualified
    summary = await service.get_my_summary("referrer-q")
    assert summary["qualified_count"] == 1


@pytest.mark.asyncio
async def test_kafka_style_idempotent_attribute(service: ReferralService) -> None:
    code = await service.get_or_create_code("referrer-id", email="id@example.com")
    first = await service.attribute(
        referee_user_id="referee-id",
        email="nid@example.com",
        referral_code=code.code,
        device_id="device-idem-0000001",
        idempotency_key="user-registered:referee-id",
    )
    second = await service.attribute(
        referee_user_id="referee-id",
        email="nid@example.com",
        referral_code=code.code,
        device_id="device-idem-0000001",
        idempotency_key="user-registered:referee-id",
    )
    assert first is not None and second is not None
    assert first.id == second.id


def test_gmail_normalize() -> None:
    assert normalize_email("A.B+tag@Gmail.com") == "ab@gmail.com"
    assert email_fingerprint("a.b@gmail.com") == email_fingerprint("ab+x@googlemail.com")

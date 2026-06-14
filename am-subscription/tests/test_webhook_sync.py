from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest

from am_subscription.services.subscription_service import SubscriptionService
from am_subscription.models.db import Subscription, SubscriptionState, ProviderMap, SubscriptionAudit
from am_subscription.schemas.subscription import PlanDTO, PlanLimitsDTO, PlanEntitlementsDTO


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_process_billing_webhook_subscription_started_new():
    session = AsyncMock()
    session.add = MagicMock()
    catalog = MagicMock()
    provider = MagicMock()
    events = MagicMock()

    # Mock catalog
    mock_plan = PlanDTO(
        code="am_pro",
        name="Pro",
        interval="monthly",
        description="Pro plan",
        amount_inr=999,
        features=[],
        limits=PlanLimitsDTO(document_parses=50, portfolios=5, ai_portfolio_summaries=20, api_calls=50000),
        entitlements=PlanEntitlementsDTO(live_market_data=True, realtime_indices=True, tradingview_charts=True, basket_trading=False)
    )
    catalog.get_plan.return_value = mock_plan

    service = SubscriptionService(
        session=session,
        catalog=catalog,
        provider=provider,
        events=events,
        default_plan_code="am_free",
    )

    mock_sub_result = MagicMock()
    mock_sub_result.scalar_one_or_none.return_value = None

    mock_map_result = MagicMock()
    mock_map_result.scalar_one_or_none.return_value = None

    session.execute.side_effect = [mock_sub_result, mock_map_result]

    user_id = "test-user-123"
    await service.process_billing_webhook(
        webhook_type="subscription.started",
        user_id=user_id,
        plan_code="am_pro",
        provider_sub_id="lago-sub-999",
        correlation_id="corr-111"
    )

    # Verify additions to the database session
    added_objects = [args[0] for args, _ in session.add.call_args_list]

    subscriptions = [o for o in added_objects if isinstance(o, Subscription)]
    audits = [o for o in added_objects if isinstance(o, SubscriptionAudit)]
    maps = [o for o in added_objects if isinstance(o, ProviderMap)]

    assert len(subscriptions) == 1
    assert subscriptions[0].user_id == user_id
    assert subscriptions[0].plan_code == "am_pro"
    assert subscriptions[0].state == SubscriptionState.active
    assert subscriptions[0].provider_subscription_id == "lago-sub-999"
    assert subscriptions[0].billing_interval == "monthly"

    assert len(audits) == 1
    assert audits[0].actor == "billing_provider"
    assert audits[0].reason == "webhook_subscription_created"
    assert audits[0].next_state == "active"
    assert audits[0].previous_state is None

    assert len(maps) == 1
    assert maps[0].user_id == user_id
    assert maps[0].external_customer_id == f"am-user-{user_id}"

    assert session.flush.call_count == 1
    assert session.commit.call_count == 1


@pytest.mark.anyio
async def test_process_billing_webhook_subscription_started_existing():
    session = AsyncMock()
    session.add = MagicMock()
    catalog = MagicMock()
    provider = MagicMock()
    events = MagicMock()

    mock_plan = PlanDTO(
        code="am_premium",
        name="Premium",
        interval="monthly",
        description="Premium plan",
        amount_inr=1999,
        features=[],
        limits=PlanLimitsDTO(document_parses=200, portfolios=20, ai_portfolio_summaries=100, api_calls=250000),
        entitlements=PlanEntitlementsDTO(live_market_data=True, realtime_indices=True, tradingview_charts=True, basket_trading=True)
    )
    catalog.get_plan.return_value = mock_plan

    existing_sub = Subscription(
        id=uuid4(),
        user_id="test-user-123",
        plan_code="am_pro",
        state=SubscriptionState.active,
        provider_subscription_id="lago-sub-111",
        billing_interval="monthly"
    )

    service = SubscriptionService(
        session=session,
        catalog=catalog,
        provider=provider,
        events=events,
        default_plan_code="am_free",
    )

    mock_sub_result = MagicMock()
    mock_sub_result.scalar_one_or_none.return_value = existing_sub

    existing_map = ProviderMap(
        user_id="test-user-123",
        provider="lago",
        external_customer_id="am-user-test-user-123"
    )
    mock_map_result = MagicMock()
    mock_map_result.scalar_one_or_none.return_value = existing_map

    session.execute.side_effect = [mock_sub_result, mock_map_result]

    await service.process_billing_webhook(
        webhook_type="subscription.started",
        user_id="test-user-123",
        plan_code="am_premium",
        provider_sub_id="lago-sub-222",
        correlation_id="corr-222"
    )

    assert existing_sub.plan_code == "am_premium"
    assert existing_sub.provider_subscription_id == "lago-sub-222"
    assert existing_sub.state == SubscriptionState.active

    added_objects = [args[0] for args, _ in session.add.call_args_list]
    audits = [o for o in added_objects if isinstance(o, SubscriptionAudit)]
    subscriptions = [o for o in added_objects if isinstance(o, Subscription)]
    maps = [o for o in added_objects if isinstance(o, ProviderMap)]

    assert len(audits) == 1
    assert audits[0].actor == "billing_provider"
    assert audits[0].reason == "webhook_subscription_started"
    assert audits[0].previous_state == "active"
    assert audits[0].next_state == "active"
    assert audits[0].metadata_json == {"previous_plan": "am_pro", "new_plan": "am_premium"}

    assert len(subscriptions) == 0
    assert len(maps) == 0

    assert session.commit.call_count == 1


@pytest.mark.anyio
async def test_process_billing_webhook_subscription_terminated():
    session = AsyncMock()
    session.add = MagicMock()
    catalog = MagicMock()
    provider = MagicMock()
    events = MagicMock()

    existing_sub = Subscription(
        id=uuid4(),
        user_id="test-user-123",
        plan_code="am_pro",
        state=SubscriptionState.active,
        provider_subscription_id="lago-sub-111",
        billing_interval="monthly"
    )

    service = SubscriptionService(
        session=session,
        catalog=catalog,
        provider=provider,
        events=events,
        default_plan_code="am_free",
    )

    mock_sub_result = MagicMock()
    mock_sub_result.scalar_one_or_none.return_value = existing_sub
    session.execute.return_value = mock_sub_result

    await service.process_billing_webhook(
        webhook_type="subscription.terminated",
        user_id="test-user-123",
        plan_code=None,
        provider_sub_id=None,
        correlation_id="corr-333"
    )

    assert existing_sub.state == SubscriptionState.cancelled

    added_objects = [args[0] for args, _ in session.add.call_args_list]
    audits = [o for o in added_objects if isinstance(o, SubscriptionAudit)]
    assert len(audits) == 1
    assert audits[0].actor == "billing_provider"
    assert audits[0].reason == "webhook_subscription_terminated"
    assert audits[0].previous_state == "active"
    assert audits[0].next_state == "cancelled"

    assert session.commit.call_count == 1


@pytest.mark.anyio
async def test_process_billing_webhook_payment_failure():
    session = AsyncMock()
    session.add = MagicMock()
    catalog = MagicMock()
    provider = MagicMock()
    events = MagicMock()

    existing_sub = Subscription(
        id=uuid4(),
        user_id="test-user-123",
        plan_code="am_pro",
        state=SubscriptionState.active,
        provider_subscription_id="lago-sub-111",
        billing_interval="monthly"
    )

    service = SubscriptionService(
        session=session,
        catalog=catalog,
        provider=provider,
        events=events,
        default_plan_code="am_free",
    )

    mock_sub_result = MagicMock()
    mock_sub_result.scalar_one_or_none.return_value = existing_sub
    session.execute.return_value = mock_sub_result

    await service.process_billing_webhook(
        webhook_type="invoice.payment_failure",
        user_id="test-user-123",
        plan_code=None,
        provider_sub_id=None,
        correlation_id="corr-444"
    )

    assert existing_sub.state == SubscriptionState.suspended

    added_objects = [args[0] for args, _ in session.add.call_args_list]
    audits = [o for o in added_objects if isinstance(o, SubscriptionAudit)]
    assert len(audits) == 1
    assert audits[0].actor == "billing_provider"
    assert audits[0].reason == "webhook_payment_failure"
    assert audits[0].previous_state == "active"
    assert audits[0].next_state == "suspended"

    assert session.commit.call_count == 1

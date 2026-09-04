from datetime import datetime
from uuid import UUID

from am_platform_common import BaseDTO
from am_subscription.models.db import SubscriptionState


class PlanEntitlementsDTO(BaseDTO):
    live_market_data: bool = False
    realtime_indices: bool = False
    tradingview_charts: bool = False
    basket_trading: bool = False
    custom_ai_bots: bool = False
    predictive_analytics: bool = False


class PlanLimitsDTO(BaseDTO):
    document_parses: int = 0
    portfolios: int = 0
    ai_portfolio_summaries: int = 0
    api_calls: int = 0


class PlanDTO(BaseDTO):
    code: str
    name: str
    interval: str
    description: str
    amount_inr: int
    features: list[str]
    limits: PlanLimitsDTO
    entitlements: PlanEntitlementsDTO


class UsageSnapshotDTO(BaseDTO):
    metric_code: str
    used: int
    limit: int
    remaining: int


class SubscriptionDTO(BaseDTO):
    id: UUID
    user_id: str
    tenant_id: str | None
    plan_code: str
    plan_name: str
    state: SubscriptionState
    billing_interval: str
    current_period_start: datetime | None
    current_period_end: datetime | None
    limits: PlanLimitsDTO
    entitlements: PlanEntitlementsDTO
    usage: list[UsageSnapshotDTO]
    created_at: datetime
    updated_at: datetime


class CreateSubscriptionRequest(BaseDTO):
    plan_code: str | None = None
    billing_interval: str = "monthly"
    tenant_id: str | None = None


class UpgradeSubscriptionRequest(BaseDTO):
    plan_code: str
    billing_interval: str | None = None
    reason: str | None = None


class StateChangeRequest(BaseDTO):
    reason: str | None = None


class UsageHistoryItemDTO(BaseDTO):
    metric_code: str
    quantity: int
    recorded_at: datetime
    idempotency_key: str


class UsageHistoryResponse(BaseDTO):
    items: list[UsageHistoryItemDTO]
    total: int

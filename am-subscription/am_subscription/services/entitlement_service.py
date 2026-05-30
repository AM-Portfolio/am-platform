from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from am_platform_common import ForbiddenError, NotFoundError, QuotaExceededError

from am_subscription.core.plan_catalog import PlanCatalog
from am_subscription.core.state_machine import ACTIVE_STATES, assert_active_for_usage
from am_subscription.models.db import MeterBuffer, ProviderMap, Subscription
from am_subscription.providers.lago_provider import LagoProvider
from am_subscription.schemas.entitlement import (
    EntitlementCheckRequest,
    EntitlementCheckResponse,
    EntitlementsResponse,
)
from am_subscription.schemas.meter import MeterRequest, MeterResponse
from am_subscription.services.event_publisher import EventPublisher

FEATURE_TO_ENTITLEMENT: dict[str, str] = {
    "live_market_data": "live_market_data",
    "realtime_indices": "realtime_indices",
    "tradingview_charts": "tradingview_charts",
    "basket_trading": "basket_trading",
    "custom_ai_bots": "custom_ai_bots",
    "predictive_analytics": "predictive_analytics",
}

ACTION_TO_METRIC: dict[str, str] = {
    "document.parse": "document_parses",
    "portfolio.create": "portfolios",
    "ai.summary": "ai_portfolio_summaries",
    "api.call": "api_calls",
}


class EntitlementService:
    def __init__(
        self,
        session: AsyncSession,
        catalog: PlanCatalog,
        events: EventPublisher,
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._events = events

    async def get_entitlements(self, user_id: str) -> EntitlementsResponse:
        subscription = await self._require_subscription(user_id)
        plan = self._catalog.get_plan(subscription.plan_code)
        usage = await self._usage_totals(user_id)
        return EntitlementsResponse(
            user_id=user_id,
            plan_code=plan.code,
            state=subscription.state.value,
            entitlements=plan.entitlements.model_dump(),
            limits=plan.limits.model_dump(),
            usage=usage,
        )

    async def check(self, payload: EntitlementCheckRequest) -> EntitlementCheckResponse:
        subscription = await self._require_subscription(payload.user_id)
        if subscription.state.value not in ACTIVE_STATES:
            return EntitlementCheckResponse(
                allowed=False,
                reason=f"subscription_state_{subscription.state.value}",
                plan_code=subscription.plan_code,
                feature=payload.feature,
                action=payload.action,
            )

        plan = self._catalog.get_plan(subscription.plan_code)
        entitlement_key = FEATURE_TO_ENTITLEMENT.get(payload.feature, payload.feature)
        entitlements = plan.entitlements.model_dump()
        if entitlement_key in entitlements and not entitlements[entitlement_key]:
            return EntitlementCheckResponse(
                allowed=False,
                reason="feature_not_in_plan",
                plan_code=plan.code,
                feature=payload.feature,
                action=payload.action,
            )

        metric_code = ACTION_TO_METRIC.get(payload.action)
        if metric_code:
            limits = plan.limits.model_dump()
            limit = limits.get(metric_code)
            if limit is not None:
                used = await self._usage_total(payload.user_id, metric_code)
                remaining = limit - used
                if remaining < payload.quantity:
                    await self._events.quota_exceeded(
                        tenant_id=payload.tenant_id or payload.user_id,
                        user_id=payload.user_id,
                        correlation_id=payload.idempotency_key,
                        idempotency_key=payload.idempotency_key,
                        payload={
                            "metric_code": metric_code,
                            "limit": limit,
                            "used": used,
                            "requested": payload.quantity,
                        },
                    )
                    raise QuotaExceededError(
                        message=f"Quota exceeded for {metric_code}",
                        details={"limit": limit, "used": used, "remaining": max(remaining, 0)},
                    )
                return EntitlementCheckResponse(
                    allowed=True,
                    plan_code=plan.code,
                    feature=payload.feature,
                    action=payload.action,
                    remaining=remaining - payload.quantity,
                )

        return EntitlementCheckResponse(
            allowed=True,
            plan_code=plan.code,
            feature=payload.feature,
            action=payload.action,
        )

    async def _require_subscription(self, user_id: str) -> Subscription:
        result = await self._session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            raise NotFoundError(message="Subscription not found for user")
        return subscription

    async def _usage_totals(self, user_id: str) -> dict[str, int]:
        result = await self._session.execute(
            select(MeterBuffer.metric_code, func.coalesce(func.sum(MeterBuffer.quantity), 0))
            .where(MeterBuffer.user_id == user_id)
            .group_by(MeterBuffer.metric_code)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def _usage_total(self, user_id: str, metric_code: str) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.sum(MeterBuffer.quantity), 0)).where(
                MeterBuffer.user_id == user_id,
                MeterBuffer.metric_code == metric_code,
            )
        )
        return int(result.scalar_one())


class MeteringService:
    def __init__(
        self,
        session: AsyncSession,
        provider: LagoProvider,
        events: EventPublisher,
    ) -> None:
        self._session = session
        self._provider = provider
        self._events = events

    async def record(self, payload: MeterRequest) -> MeterResponse:
        subscription = await self._session.execute(
            select(Subscription).where(Subscription.user_id == payload.user_id)
        )
        sub = subscription.scalar_one_or_none()
        if not sub:
            raise NotFoundError(message="Subscription not found for user")
        assert_active_for_usage(sub.state.value)

        existing = await self._session.execute(
            select(MeterBuffer).where(MeterBuffer.idempotency_key == payload.idempotency_key)
        )
        if existing.scalar_one_or_none():
            return MeterResponse(
                accepted=True,
                duplicate=True,
                metric_code=payload.metric_code,
                quantity=payload.quantity,
                synced=True,
            )

        provider_map = await self._session.execute(
            select(ProviderMap).where(ProviderMap.user_id == payload.user_id)
        )
        mapping = provider_map.scalar_one_or_none()
        if not mapping:
            raise ForbiddenError(message="Provider mapping missing for user")

        row = MeterBuffer(
            user_id=payload.user_id,
            metric_code=payload.metric_code,
            quantity=payload.quantity,
            idempotency_key=payload.idempotency_key,
            properties_json=payload.properties,
        )
        self._session.add(row)
        await self._session.flush()

        synced = False
        try:
            await self._provider.send_usage_event(
                mapping.external_customer_id,
                payload.metric_code,
                payload.quantity,
                transaction_id=payload.idempotency_key,
                properties=payload.properties,
            )
            row.synced_at = row.created_at
            synced = True
        except Exception:
            # Buffer locally; background sync can retry later.
            synced = False

        await self._session.commit()
        return MeterResponse(
            accepted=True,
            duplicate=False,
            metric_code=payload.metric_code,
            quantity=payload.quantity,
            synced=synced,
        )

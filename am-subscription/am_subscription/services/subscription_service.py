from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from am_platform_common import ConflictError, NotFoundError

from am_subscription.core.plan_catalog import PlanCatalog
from am_subscription.core.state_machine import validate_transition
from am_subscription.models.db import (
    MeterBuffer,
    ProviderMap,
    Subscription,
    SubscriptionAudit,
    SubscriptionState,
)
from am_subscription.providers.lago_provider import LagoProvider
from am_subscription.schemas.subscription import (
    CreateSubscriptionRequest,
    PlanDTO,
    SubscriptionDTO,
    UpgradeSubscriptionRequest,
    UsageHistoryItemDTO,
    UsageHistoryResponse,
    UsageSnapshotDTO,
)
from am_subscription.core.log_utils import get_logger
from am_subscription.services.event_publisher import EventPublisher

logger = get_logger("subscription_service")


class SubscriptionService:
    def __init__(
        self,
        session: AsyncSession,
        catalog: PlanCatalog,
        provider: LagoProvider,
        events: EventPublisher,
        default_plan_code: str,
    ) -> None:
        self._session = session
        self._catalog = catalog
        self._provider = provider
        self._events = events
        self._default_plan_code = default_plan_code

    async def list_plans(self, interval: str | None = None) -> list[PlanDTO]:
        return self._catalog.list_plans(interval=interval)

    async def get_by_user(self, user_id: str) -> Subscription | None:
        result = await self._session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        user_id: str,
        payload: CreateSubscriptionRequest,
        *,
        actor: str,
        correlation_id: str,
    ) -> SubscriptionDTO:
        logger.info(
            "get_or_create subscription",
            extra={"user_id": user_id, "plan_code": payload.plan_code, "correlation_id": correlation_id},
        )
        existing = await self.get_by_user(user_id)
        if existing:
            logger.info("subscription exists", extra={"user_id": user_id, "subscription_id": str(existing.id)})
            return await self.to_dto(existing)

        plan_code = self._catalog.resolve_plan_code(
            payload.plan_code or self._default_plan_code,
            payload.billing_interval,
        )
        plan = self._catalog.get_plan(plan_code)
        logger.info("provisioning with Lago", extra={"user_id": user_id, "plan_code": plan.code})

        external_customer_id = f"am-user-{user_id}"
        customer = await self._provider.ensure_customer(external_customer_id)
        sub_external_id = f"am-sub-{user_id}"
        provider_sub = await self._provider.create_subscription(
            external_customer_id,
            plan.code,
            external_id=sub_external_id,
        )
        logger.info(
            "Lago subscription created",
            extra={
                "user_id": user_id,
                "external_customer_id": external_customer_id,
                "provider_subscription_id": provider_sub.get("external_id") or sub_external_id,
            },
        )

        subscription = Subscription(
            user_id=user_id,
            tenant_id=payload.tenant_id,
            plan_code=plan.code,
            state=SubscriptionState.active,
            provider="lago",
            provider_subscription_id=provider_sub.get("external_id") or sub_external_id,
            billing_interval=plan.interval,
        )
        self._session.add(subscription)

        provider_map = ProviderMap(
            user_id=user_id,
            provider="lago",
            external_customer_id=external_customer_id,
            provider_customer_id=customer.get("lago_id"),
        )
        self._session.add(provider_map)
        await self._session.flush()
        await self._append_audit(
            subscription.id,
            actor=actor,
            previous_state=None,
            next_state=subscription.state.value,
            reason="subscription_created",
            correlation_id=correlation_id,
        )
        await self._session.commit()
        await self._session.refresh(subscription)

        await self._events.subscription_created(
            tenant_id=payload.tenant_id or user_id,
            user_id=user_id,
            correlation_id=correlation_id,
            idempotency_key=f"sub-create-{user_id}",
            payload={"plan_code": plan.code, "state": subscription.state.value},
        )
        return await self.to_dto(subscription)

    async def cancel(
        self,
        subscription_id: UUID,
        user_id: str,
        *,
        actor: str,
        reason: str | None,
        correlation_id: str,
    ) -> SubscriptionDTO:
        subscription = await self._get_owned(subscription_id, user_id)
        await self._transition(
            subscription,
            SubscriptionState.cancelled,
            actor=actor,
            reason=reason or "user_cancelled",
            correlation_id=correlation_id,
        )
        if subscription.provider_subscription_id:
            await self._provider.cancel_subscription(subscription.provider_subscription_id)
        await self._session.commit()
        await self._session.refresh(subscription)
        return await self.to_dto(subscription)

    async def pause(
        self,
        subscription_id: UUID,
        user_id: str,
        *,
        actor: str,
        reason: str | None,
        correlation_id: str,
    ) -> SubscriptionDTO:
        subscription = await self._get_owned(subscription_id, user_id)
        await self._transition(
            subscription,
            SubscriptionState.paused,
            actor=actor,
            reason=reason or "user_paused",
            correlation_id=correlation_id,
        )
        await self._session.commit()
        await self._session.refresh(subscription)
        return await self.to_dto(subscription)

    async def resume(
        self,
        subscription_id: UUID,
        user_id: str,
        *,
        actor: str,
        reason: str | None,
        correlation_id: str,
    ) -> SubscriptionDTO:
        subscription = await self._get_owned(subscription_id, user_id)
        await self._transition(
            subscription,
            SubscriptionState.active,
            actor=actor,
            reason=reason or "user_resumed",
            correlation_id=correlation_id,
        )
        await self._session.commit()
        await self._session.refresh(subscription)
        return await self.to_dto(subscription)

    async def upgrade(
        self,
        subscription_id: UUID,
        user_id: str,
        payload: UpgradeSubscriptionRequest,
        *,
        actor: str,
        correlation_id: str,
    ) -> SubscriptionDTO:
        subscription = await self._get_owned(subscription_id, user_id)
        interval = payload.billing_interval or subscription.billing_interval
        new_plan_code = self._catalog.resolve_plan_code(payload.plan_code, interval)
        plan = self._catalog.get_plan(new_plan_code)

        if subscription.provider_subscription_id:
            await self._provider.change_plan(subscription.provider_subscription_id, plan.code)

        previous_plan = subscription.plan_code
        subscription.plan_code = plan.code
        subscription.billing_interval = plan.interval
        subscription.updated_at = datetime.now(timezone.utc)
        await self._append_audit(
            subscription.id,
            actor=actor,
            previous_state=subscription.state.value,
            next_state=subscription.state.value,
            reason=payload.reason or "plan_upgrade",
            correlation_id=correlation_id,
            metadata={"previous_plan": previous_plan, "new_plan": plan.code},
        )
        await self._session.commit()
        await self._session.refresh(subscription)

        await self._events.subscription_changed(
            tenant_id=subscription.tenant_id or user_id,
            user_id=user_id,
            correlation_id=correlation_id,
            idempotency_key=f"sub-upgrade-{subscription.id}-{plan.code}",
            payload={
                "previous_plan": previous_plan,
                "plan_code": plan.code,
                "state": subscription.state.value,
            },
        )
        return await self.to_dto(subscription)

    async def usage_history(self, user_id: str, *, limit: int = 50) -> UsageHistoryResponse:
        result = await self._session.execute(
            select(MeterBuffer)
            .where(MeterBuffer.user_id == user_id)
            .order_by(MeterBuffer.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
        items = [
            UsageHistoryItemDTO(
                metric_code=row.metric_code,
                quantity=row.quantity,
                recorded_at=row.created_at,
                idempotency_key=row.idempotency_key,
            )
            for row in rows
        ]
        count_result = await self._session.execute(
            select(func.count()).select_from(MeterBuffer).where(MeterBuffer.user_id == user_id)
        )
        total = int(count_result.scalar_one())
        return UsageHistoryResponse(items=items, total=total)

    async def to_dto(self, subscription: Subscription) -> SubscriptionDTO:
        plan = self._catalog.get_plan(subscription.plan_code)
        usage = await self._usage_snapshots(subscription.user_id, plan)
        return SubscriptionDTO(
            id=subscription.id,
            user_id=subscription.user_id,
            tenant_id=subscription.tenant_id,
            plan_code=subscription.plan_code,
            plan_name=plan.name,
            state=subscription.state.value,
            billing_interval=subscription.billing_interval,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            limits=plan.limits,
            entitlements=plan.entitlements,
            usage=usage,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        )

    async def _usage_snapshots(self, user_id: str, plan: PlanDTO) -> list[UsageSnapshotDTO]:
        result = await self._session.execute(
            select(MeterBuffer.metric_code, func.coalesce(func.sum(MeterBuffer.quantity), 0))
            .where(MeterBuffer.user_id == user_id)
            .group_by(MeterBuffer.metric_code)
        )
        used_by_metric = {row[0]: int(row[1]) for row in result.all()}
        snapshots: list[UsageSnapshotDTO] = []
        for metric_code, limit in plan.limits.model_dump().items():
            if limit <= 0:
                continue
            used = used_by_metric.get(metric_code, 0)
            snapshots.append(
                UsageSnapshotDTO(
                    metric_code=metric_code,
                    used=used,
                    limit=limit,
                    remaining=max(limit - used, 0),
                )
            )
        return snapshots

    async def _get_owned(self, subscription_id: UUID, user_id: str) -> Subscription:
        result = await self._session.execute(
            select(Subscription).where(
                Subscription.id == subscription_id,
                Subscription.user_id == user_id,
            )
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            raise NotFoundError(message="Subscription not found")
        return subscription

    async def _transition(
        self,
        subscription: Subscription,
        target: SubscriptionState,
        *,
        actor: str,
        reason: str,
        correlation_id: str,
    ) -> None:
        current = subscription.state.value
        validate_transition(current, target.value)
        previous = current
        subscription.state = target
        subscription.updated_at = datetime.now(timezone.utc)
        await self._append_audit(
            subscription.id,
            actor=actor,
            previous_state=previous,
            next_state=target.value,
            reason=reason,
            correlation_id=correlation_id,
        )
        if target == SubscriptionState.suspended:
            await self._events.subscription_suspended(
                tenant_id=subscription.tenant_id or subscription.user_id,
                user_id=subscription.user_id,
                correlation_id=correlation_id,
                idempotency_key=f"sub-suspended-{subscription.id}",
                payload={"state": target.value, "plan_code": subscription.plan_code},
            )
        else:
            await self._events.subscription_changed(
                tenant_id=subscription.tenant_id or subscription.user_id,
                user_id=subscription.user_id,
                correlation_id=correlation_id,
                idempotency_key=f"sub-change-{subscription.id}-{target.value}",
                payload={"previous_state": previous, "state": target.value, "plan_code": subscription.plan_code},
            )

    async def _append_audit(
        self,
        subscription_id: UUID,
        *,
        actor: str,
        previous_state: str | None,
        next_state: str,
        reason: str,
        correlation_id: str,
        metadata: dict | None = None,
    ) -> None:
        self._session.add(
            SubscriptionAudit(
                subscription_id=subscription_id,
                actor=actor,
                reason=reason,
                previous_state=previous_state,
                next_state=next_state,
                correlation_id=correlation_id,
                metadata_json=metadata,
            )
        )

    async def process_billing_webhook(
        self,
        webhook_type: str,
        user_id: str,
        plan_code: str | None,
        provider_sub_id: str | None,
        correlation_id: str,
    ) -> None:
        logger.info(
            "process_billing_webhook",
            extra={
                "webhook_type": webhook_type,
                "user_id": user_id,
                "plan_code": plan_code,
                "provider_sub_id": provider_sub_id,
                "correlation_id": correlation_id,
            },
        )
        existing = await self.get_by_user(user_id)

        if webhook_type == "subscription.started":
            if not plan_code:
                logger.error("plan_code is missing for subscription.started", extra={"user_id": user_id})
                return

            plan = self._catalog.get_plan(plan_code)

            if existing:
                previous_state = existing.state.value
                previous_plan = existing.plan_code

                # Direct update bypassing the state machine, as billing provider is source of truth
                existing.state = SubscriptionState.active
                existing.plan_code = plan.code
                existing.billing_interval = plan.interval
                if provider_sub_id:
                    existing.provider_subscription_id = provider_sub_id
                existing.updated_at = datetime.now(timezone.utc)

                await self._append_audit(
                    existing.id,
                    actor="billing_provider",
                    previous_state=previous_state,
                    next_state=existing.state.value,
                    reason="webhook_subscription_started",
                    correlation_id=correlation_id,
                    metadata={"previous_plan": previous_plan, "new_plan": plan.code},
                )
            else:
                # Create a new subscription
                subscription = Subscription(
                    user_id=user_id,
                    plan_code=plan.code,
                    state=SubscriptionState.active,
                    provider="lago",
                    provider_subscription_id=provider_sub_id,
                    billing_interval=plan.interval,
                )
                self._session.add(subscription)
                await self._session.flush()

                await self._append_audit(
                    subscription.id,
                    actor="billing_provider",
                    previous_state=None,
                    next_state=subscription.state.value,
                    reason="webhook_subscription_created",
                    correlation_id=correlation_id,
                    metadata={"plan_code": plan.code},
                )

            # Ensure ProviderMap exists
            result_map = await self._session.execute(
                select(ProviderMap).where(ProviderMap.user_id == user_id)
            )
            existing_map = result_map.scalar_one_or_none()
            if not existing_map:
                external_customer_id = f"am-user-{user_id}"
                provider_map = ProviderMap(
                    user_id=user_id,
                    provider="lago",
                    external_customer_id=external_customer_id,
                )
                self._session.add(provider_map)

            await self._session.commit()

        elif webhook_type == "subscription.terminated":
            if existing:
                previous_state = existing.state.value
                existing.state = SubscriptionState.cancelled
                existing.updated_at = datetime.now(timezone.utc)

                await self._append_audit(
                    existing.id,
                    actor="billing_provider",
                    previous_state=previous_state,
                    next_state=existing.state.value,
                    reason="webhook_subscription_terminated",
                    correlation_id=correlation_id,
                )
                await self._session.commit()
            else:
                logger.warning(
                    "subscription.terminated received but no existing subscription found",
                    extra={"user_id": user_id},
                )

        elif webhook_type == "invoice.payment_failure":
            if existing:
                previous_state = existing.state.value
                existing.state = SubscriptionState.suspended
                existing.updated_at = datetime.now(timezone.utc)

                await self._append_audit(
                    existing.id,
                    actor="billing_provider",
                    previous_state=previous_state,
                    next_state=existing.state.value,
                    reason="webhook_payment_failure",
                    correlation_id=correlation_id,
                )
                await self._session.commit()
            else:
                logger.warning(
                    "invoice.payment_failure received but no existing subscription found",
                    extra={"user_id": user_id},
                )


from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from am_platform_common import EventEnvelope

from am_subscription.core.config import SubscriptionSettings

logger = logging.getLogger(__name__)


class EventPublisher:
    """Kafka publisher stub — logs canonical events until aiokafka producer is wired."""

    def __init__(self, settings: SubscriptionSettings) -> None:
        self._settings = settings

    async def publish(
        self,
        event_type: str,
        *,
        tenant_id: str,
        user_id: str | None,
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> None:
        envelope = EventEnvelope(
            event_type=event_type,
            producer=self._settings.app_name,
            tenant_id=tenant_id,
            user_id=user_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        logger.info(
            "event_published",
            extra={
                "event_type": event_type,
                "event_id": str(envelope.event_id),
                "user_id": user_id,
                "kafka_enabled": self._settings.kafka_enabled,
            },
        )
        if self._settings.kafka_enabled:
            # Phase 4 will replace this with aiokafka producer.
            pass

    async def subscription_created(self, **kwargs: Any) -> None:
        await self.publish("am.subscription.created.v1", **kwargs)

    async def subscription_changed(self, **kwargs: Any) -> None:
        await self.publish("am.subscription.changed.v1", **kwargs)

    async def subscription_suspended(self, **kwargs: Any) -> None:
        await self.publish("am.subscription.suspended.v1", **kwargs)

    async def quota_exceeded(self, **kwargs: Any) -> None:
        await self.publish("am.usage.quota_exceeded.v1", **kwargs)

    @staticmethod
    def new_correlation_id() -> str:
        return str(uuid4())

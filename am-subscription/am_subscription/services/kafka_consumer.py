import asyncio
import json
import logging
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.helpers import create_ssl_context

from am_subscription.core.config import get_settings
from am_subscription.core.database import get_session_factory
from am_subscription.core.plan_catalog import get_plan_catalog
from am_subscription.models.db import SubscriptionState
from am_subscription.providers.lago_provider import LagoProvider
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


class SubscriptionKafkaConsumer:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.consumer: AIOKafkaConsumer | None = None
        self._task: asyncio.Task | None = None
        self._session_factory = get_session_factory()
        self._lago_provider = LagoProvider(self.settings)
        self._catalog = get_plan_catalog()
        self._events = EventPublisher(self.settings)

    async def start(self) -> None:
        if not self.settings.kafka_enabled:
            logger.info("Kafka consumer disabled in settings.")
            return

        kwargs: dict[str, Any] = {
            "bootstrap_servers": self.settings.kafka_bootstrap_servers,
            "group_id": "am-subscription-group",
            "auto_offset_reset": "earliest",
            "security_protocol": self.settings.kafka_security_protocol,
        }

        if self.settings.kafka_username and self.settings.kafka_password:
            kwargs["sasl_mechanism"] = self.settings.kafka_sasl_mechanism
            kwargs["sasl_plain_username"] = self.settings.kafka_username
            kwargs["sasl_plain_password"] = self.settings.kafka_password

        if self.settings.kafka_security_protocol.endswith("SSL"):
            kwargs["ssl_context"] = create_ssl_context()

        topics = [t.strip() for t in self.settings.kafka_topics.split(",") if t.strip()]

        try:
            self.consumer = AIOKafkaConsumer(*topics, **kwargs)
            await self.consumer.start()
            logger.info(f"Kafka consumer started. Listening to {topics}")
            self._task = asyncio.create_task(self._consume_loop())
        except Exception as e:
            logger.error(f"Failed to start Kafka consumer: {e}")
            self.consumer = None

    async def _consume_loop(self) -> None:
        if not self.consumer:
            return

        try:
            async for msg in self.consumer:
                try:
                    payload = json.loads(msg.value.decode("utf-8"))
                    await self._process_event(payload)
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Fatal error in consumer loop: {e}")

    async def _process_event(self, payload: dict[str, Any]) -> None:
        event_type = payload.get("type") or payload.get("event_type")
        if not event_type:
            return

        if event_type == "user.permanently_deleted.v1":
            data = payload.get("data") or payload.get("payload") or {}
            user_id = data.get("user_id") or payload.get("user_id")
            if not user_id:
                return

            logger.info(f"Handling permanent deletion for user: {user_id}")
            correlation_id = EventPublisher.new_correlation_id()
            async with self._session_factory() as session:
                sub_service = SubscriptionService(
                    session,
                    self._catalog,
                    self._lago_provider,
                    self._events,
                    self.settings.default_plan_code,
                )
                # Retry loop for database and Lago provider transient failures
                max_retries = 3
                retry_delay = 1.0
                for attempt in range(1, max_retries + 1):
                    try:
                        sub = await sub_service.get_by_user(user_id)
                        if sub and sub.state in (
                            SubscriptionState.active,
                            SubscriptionState.past_due,
                            SubscriptionState.paused,
                        ):
                            logger.info(
                                f"Canceling subscription {sub.id} for deleted user {user_id} (Attempt {attempt})"
                            )
                            await sub_service.cancel(
                                sub.id,
                                user_id,
                                actor="system:kafka-consumer",
                                reason="user_permanently_deleted",
                                correlation_id=correlation_id,
                            )
                        else:
                            logger.info(
                                f"No active subscription found for deleted user {user_id}"
                            )
                        break
                    except Exception as e:
                        if attempt == max_retries:
                            logger.error(
                                f"CRITICAL: Failed to cancel subscription for user {user_id} after {max_retries} attempts: {e}. Manual intervention required."
                            )
                        else:
                            logger.warning(
                                f"Transient failure during user subscription cancellation (attempt {attempt}/{max_retries}): {e}. Retrying in {retry_delay}s..."
                            )
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped.")


consumer_instance = SubscriptionKafkaConsumer()

from __future__ import annotations

import asyncio
import json
from typing import Any

from aiokafka import AIOKafkaConsumer
from aiokafka.helpers import create_ssl_context

from am_notification.core.config import NotificationSettings
from am_notification.core.log_utils import get_logger
from am_notification.services.notification_service import NotificationService

logger = get_logger("kafka_consumer")


class NotificationKafkaConsumer:
    def __init__(self, settings: NotificationSettings, service: NotificationService) -> None:
        self._settings = settings
        self._service = service
        self._task: asyncio.Task[None] | None = None
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    def _consumer_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "bootstrap_servers": self._settings.effective_kafka_bootstrap,
            "group_id": self._settings.kafka_group_id,
            "enable_auto_commit": False,
            "auto_offset_reset": "earliest",
            "security_protocol": self._settings.kafka_security_protocol,
        }
        if self._settings.kafka_username and self._settings.kafka_password:
            kwargs["sasl_mechanism"] = self._settings.kafka_sasl_mechanism
            kwargs["sasl_plain_username"] = self._settings.kafka_username
            kwargs["sasl_plain_password"] = self._settings.kafka_password
        if self._settings.kafka_security_protocol.endswith("SSL"):
            kwargs["ssl_context"] = create_ssl_context()
        return kwargs

    async def start(self) -> None:
        if not self._settings.kafka_enabled:
            logger.info("Kafka consumer disabled (KAFKA_ENABLED=false)")
            return
        self._running = True
        self._task = asyncio.create_task(self._start_with_retry())

    async def _start_with_retry(self) -> None:
        delay_seconds = 5
        while self._running:
            try:
                self._consumer = AIOKafkaConsumer(
                    *self._settings.kafka_topic_list, **self._consumer_kwargs()
                )
                await self._consumer.start()
                logger.info(
                    "Kafka consumer started",
                    extra={
                        "topics": self._settings.kafka_topic_list,
                        "group": self._settings.kafka_group_id,
                    },
                )
                await self._run_loop()
                return
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception(
                    "Kafka consumer unavailable; retrying",
                    extra={"retry_in_seconds": delay_seconds},
                )
                if self._consumer is not None:
                    try:
                        await self._consumer.stop()
                    except Exception:
                        pass
                    self._consumer = None
                await asyncio.sleep(delay_seconds)
                delay_seconds = min(delay_seconds * 2, 60)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._consumer is not None:
            await self._consumer.stop()

    async def _run_loop(self) -> None:
        assert self._consumer is not None
        while self._running:
            try:
                batch = await self._consumer.getmany(timeout_ms=1000, max_records=10)
                for _tp, messages in batch.items():
                    for message in messages:
                        await self._handle_message(message.value)
                if batch:
                    await self._consumer.commit()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Kafka consumer loop error")
                await asyncio.sleep(1)

    async def _handle_message(self, raw: bytes) -> None:
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Invalid Kafka message payload")
            return
        if not isinstance(envelope, dict):
            return
        await self._service.process_event_envelope(envelope)

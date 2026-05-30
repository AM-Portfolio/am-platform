from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from motor.motor_asyncio import AsyncIOMotorDatabase

from am_notification.core.log_utils import get_logger
from am_notification.providers.interface import INotificationProvider
from am_notification.services.dedupe_service import DedupeService
from am_notification.services.event_mapping import resolve_workflow
from am_notification.services.preference_service import PreferenceService

logger = get_logger("notification_service")


class NotificationService:
    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        provider: INotificationProvider,
    ) -> None:
        self._db = db
        self._provider = provider
        self._dedupe = DedupeService(db)
        self._preferences = PreferenceService(db)
        self._attempts = db.notification_delivery_attempts

    async def process_event_envelope(self, envelope: dict[str, Any]) -> dict[str, Any] | None:
        event_type = envelope.get("event_type") or envelope.get("workflow_key")
        if not event_type:
            return None

        mapping = resolve_workflow(str(event_type))
        if mapping is None and envelope.get("workflow_key"):
            mapping = {
                "workflow_key": envelope["workflow_key"],
                "category": envelope.get("category", "system"),
                "critical": bool(envelope.get("critical", False)),
            }
        if mapping is None:
            logger.debug("No workflow mapping", extra={"event_type": event_type})
            return None

        user_id = envelope.get("user_id") or envelope.get("recipient_user_id")
        if not user_id:
            logger.warning("Event missing user_id", extra={"event_type": event_type})
            return None

        event_id = str(envelope.get("event_id") or uuid4())
        workflow_key = mapping["workflow_key"]
        category = mapping["category"]
        critical = mapping["critical"]
        correlation_id = envelope.get("correlation_id")
        payload = envelope.get("payload") or {}

        channels = ["in_app", "email"]
        delivered: list[str] = []
        for channel in channels:
            if not await self._preferences.should_deliver(
                user_id, category=category, channel=channel, critical=critical
            ):
                continue
            dedupe_key = self._dedupe.build_dedupe_key(event_id, workflow_key, channel, user_id)
            if await self._dedupe.is_processed(dedupe_key):
                continue
            provider_id = await self._provider.trigger(
                workflow_key=workflow_key,
                user_id=user_id,
                payload={**payload, "channel": channel, "locale": payload.get("locale", "en")},
                idempotency_key=dedupe_key,
            )
            await self._dedupe.mark_processed(
                event_id=event_id,
                dedupe_key=dedupe_key,
                workflow_key=workflow_key,
                recipient_user_id=user_id,
                correlation_id=correlation_id,
            )
            await self._attempts.insert_one(
                {
                    "event_id": event_id,
                    "dedupe_key": dedupe_key,
                    "workflow_key": workflow_key,
                    "channel": channel,
                    "recipient_user_id": user_id,
                    "provider_message_id": provider_id,
                    "state": "delivered",
                    "correlation_id": correlation_id,
                    "created_at": datetime.now(UTC),
                }
            )
            delivered.append(channel)

        return {"event_id": event_id, "delivered_channels": delivered}

    async def send_command(self, command: dict[str, Any]) -> dict[str, Any]:
        envelope = {
            "event_id": command.get("event_id") or str(uuid4()),
            "event_type": command.get("workflow_key"),
            "workflow_key": command.get("workflow_key"),
            "user_id": command.get("recipient_user_id"),
            "correlation_id": command.get("correlation_id"),
            "payload": command.get("payload") or {},
            "critical": command.get("critical", False),
            "category": command.get("category", "system"),
        }
        result = await self.process_event_envelope(envelope)
        if result is None:
            return {"status": "skipped"}
        return {"status": "sent", **result}

    async def list_inbox(
        self, user_id: str, *, page: int = 0, page_size: int = 20, unread_only: bool = False
    ) -> list[dict[str, Any]]:
        await self._provider.ensure_subscriber(user_id)
        return await self._provider.list_in_app(
            user_id, page=page, page_size=page_size, unread_only=unread_only
        )

    async def unread_count(self, user_id: str) -> int:
        return await self._provider.unread_count(user_id)

    async def mark_read(self, user_id: str, notification_ids: list[str]) -> None:
        await self._provider.mark_read(user_id, notification_ids)

    async def mark_all_read(self, user_id: str) -> None:
        await self._provider.mark_all_read(user_id)

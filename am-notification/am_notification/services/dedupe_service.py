from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from am_notification.core.log_utils import get_logger

logger = get_logger("dedupe")


class DedupeService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db.notification_processed_events

    @staticmethod
    def build_dedupe_key(
        event_id: str, workflow_key: str, channel: str, recipient_user_id: str
    ) -> str:
        return f"{event_id}:{workflow_key}:{channel}:{recipient_user_id}"

    async def is_processed(self, dedupe_key: str) -> bool:
        existing = await self._collection.find_one(
            {"dedupe_key": dedupe_key}, {"_id": 1}
        )
        return existing is not None

    async def mark_processed(
        self,
        *,
        event_id: str,
        dedupe_key: str,
        workflow_key: str,
        recipient_user_id: str,
        correlation_id: str | None = None,
    ) -> bool:
        doc: dict[str, Any] = {
            "event_id": event_id,
            "dedupe_key": dedupe_key,
            "workflow_key": workflow_key,
            "recipient_user_id": recipient_user_id,
            "correlation_id": correlation_id,
            "processed_at": datetime.now(UTC),
        }
        try:
            await self._collection.insert_one(doc)
            return True
        except DuplicateKeyError:
            logger.info("Duplicate event skipped", extra={"dedupe_key": dedupe_key})
            return False

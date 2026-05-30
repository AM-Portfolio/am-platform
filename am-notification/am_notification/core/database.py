from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from am_notification.core.config import NotificationSettings, get_settings
from am_notification.core.log_utils import get_logger

logger = get_logger("database")

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def init_db() -> None:
    global _client, _db
    settings = get_settings()
    uri = settings.effective_mongo_uri
    logger.info(
        "Connecting to MongoDB",
        extra={"database": settings.mongo_database, "host_hint": uri.split("@")[-1][:80]},
    )
    _client = AsyncIOMotorClient(uri)
    _db = _client[settings.mongo_database]
    await _ensure_indexes(_db)


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.notification_processed_events.create_index("event_id", unique=True)
    await db.notification_processed_events.create_index("dedupe_key", unique=True)
    await db.notification_preferences.create_index("user_id", unique=True)
    await db.notification_delivery_attempts.create_index("event_id")
    await db.notification_dlq.create_index("dlq_id", unique=True)


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def close_db() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None


async def ping_db(settings: NotificationSettings | None = None) -> bool:
    settings = settings or get_settings()
    client = AsyncIOMotorClient(settings.effective_mongo_uri)
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False
    finally:
        client.close()

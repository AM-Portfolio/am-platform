from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

DEFAULT_PREFERENCES: dict[str, Any] = {
    "channels": {"email": True, "in_app": True, "sms": False},
    "categories": {
        "security": True,
        "subscription": True,
        "usage": True,
        "portfolio": True,
        "market": True,
        "trade": True,
        "system": True,
    },
    "quiet_hours": {"enabled": False, "start": "22:00", "end": "07:00", "timezone": "UTC"},
    "locale": "en",
}


class PreferenceService:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._collection = db.notification_preferences

    async def get_preferences(self, user_id: str) -> dict[str, Any]:
        doc = await self._collection.find_one({"user_id": user_id}, {"_id": 0})
        if not doc:
            return {"user_id": user_id, **DEFAULT_PREFERENCES}
        doc.pop("user_id", None)
        merged = {**DEFAULT_PREFERENCES, **doc}
        merged["user_id"] = user_id
        return merged

    async def update_preferences(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        payload = {k: v for k, v in payload.items() if k != "user_id"}
        await self._collection.update_one(
            {"user_id": user_id},
            {
                "$set": {**payload, "updated_at": datetime.now(UTC)},
                "$setOnInsert": {"user_id": user_id, "created_at": datetime.now(UTC)},
            },
            upsert=True,
        )
        return await self.get_preferences(user_id)

    async def should_deliver(
        self,
        user_id: str,
        *,
        category: str,
        channel: str,
        critical: bool,
    ) -> bool:
        if critical:
            return True
        prefs = await self.get_preferences(user_id)
        if not prefs.get("channels", {}).get(channel, True):
            return False
        return prefs.get("categories", {}).get(category, True)

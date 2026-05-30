from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NotificationCommand(BaseModel):
    event_id: str | None = None
    correlation_id: str | None = None
    workflow_key: str
    recipient_user_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    critical: bool = False
    category: str = "system"


class PreferenceUpdate(BaseModel):
    channels: dict[str, bool] | None = None
    categories: dict[str, bool] | None = None
    quiet_hours: dict[str, Any] | None = None
    locale: str | None = None


class MarkReadRequest(BaseModel):
    notification_ids: list[str] = Field(default_factory=list)

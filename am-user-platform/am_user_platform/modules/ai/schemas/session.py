"""Pydantic schemas for AI sessions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from am_platform_common import BaseDTO

from am_user_platform.modules.ai.schemas.message import MessageResponse


class SessionCreate(BaseDTO):
    product_id: str
    agent_type: str
    channel: str = "user_app"
    title: str | None = None
    id: UUID | None = None


class SessionUpdate(BaseDTO):
    title: str


class SessionResponse(BaseDTO):
    id: UUID
    user_id: str
    product_id: str
    agent_type: str
    channel: str
    title: str
    org_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class SessionListResponse(BaseDTO):
    items: list[SessionResponse]
    total: int
    limit: int
    offset: int


class SessionDetailResponse(BaseDTO):
    session: SessionResponse
    messages: list[MessageResponse]

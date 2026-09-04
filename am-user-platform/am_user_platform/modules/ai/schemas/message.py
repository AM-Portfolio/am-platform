"""Pydantic schemas for AI messages."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from am_platform_common import BaseDTO

from am_user_platform.modules.ai.models.db import MessageRole


class MessageAppendItem(BaseDTO):
    role: MessageRole
    content: str = ""
    widget_id: str | None = None
    widget_params: dict | None = None
    tools_used: list[str] | None = None
    tokens_used: int | None = None
    trace_id: str | None = None
    id: UUID | None = None


class AppendMessagesRequest(BaseDTO):
    user_id: str
    product_id: str
    agent_type: str
    channel: str = "user_app"
    messages: list[MessageAppendItem]


class MessageResponse(BaseDTO):
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    widget_id: str | None = None
    widget_params: dict | None = None
    tools_used: list[str] | None = None
    tokens_used: int | None = None
    trace_id: str | None = None
    created_at: datetime


class ContextResponse(BaseDTO):
    session_id: UUID
    messages: list[MessageResponse]

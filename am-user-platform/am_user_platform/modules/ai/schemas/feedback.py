"""Pydantic schemas for AI feedback."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from am_platform_common import BaseDTO


class FeedbackCreate(BaseDTO):
    session_id: UUID
    message_id: UUID | None = None
    agent_type: str
    rating: str
    comment: str | None = None
    trace_id: str | None = None


class FeedbackResponse(BaseDTO):
    id: UUID
    user_id: str
    session_id: UUID
    message_id: UUID | None = None
    agent_type: str
    rating: str
    comment: str | None = None
    trace_id: str | None = None
    created_at: datetime

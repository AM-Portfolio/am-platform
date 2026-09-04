"""Message append and context reads for the ai module."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from am_user_platform.core.log_utils import get_logger
from am_user_platform.modules.ai.models.db import AiMessage, AiSession, MessageRole
from am_user_platform.modules.ai.schemas.message import (
    AppendMessagesRequest,
    ContextResponse,
    MessageAppendItem,
    MessageResponse,
)
from am_user_platform.modules.ai.schemas.session import SessionCreate
from am_user_platform.modules.ai.services.helpers import (
    DEFAULT_TITLE,
    title_from_first_message,
)
from am_user_platform.modules.ai.services.session_service import SessionService

logger = get_logger("message_service")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_message_response(row: AiMessage) -> MessageResponse:
    return MessageResponse.model_validate(row)


class MessageService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sessions = SessionService(session)

    async def append_messages(
        self,
        session_id: uuid.UUID,
        payload: AppendMessagesRequest,
    ) -> list[MessageResponse]:
        ai_session = await self._resolve_session(session_id, payload)
        created: list[AiMessage] = []

        for item in payload.messages:
            row = AiMessage(
                id=item.id or uuid.uuid4(),
                session_id=ai_session.id,
                role=item.role,
                content=item.content,
                widget_id=item.widget_id,
                widget_params=item.widget_params,
                tools_used=item.tools_used,
                tokens_used=item.tokens_used,
                trace_id=item.trace_id,
            )
            self._session.add(row)
            created.append(row)

        ai_session.updated_at = _utcnow()
        self._maybe_set_title(ai_session, payload.messages)
        await self._session.flush()
        for row in created:
            await self._session.refresh(row)

        logger.info(
            "messages appended",
            extra={
                "session_id": str(session_id),
                "count": len(created),
                "user_id": payload.user_id,
            },
        )
        return [_to_message_response(row) for row in created]

    async def get_messages(
        self, session_id: uuid.UUID, user_id: str
    ) -> list[MessageResponse]:
        await self._sessions.get_session_row(session_id, user_id)
        result = await self._session.execute(
            select(AiMessage)
            .where(AiMessage.session_id == session_id)
            .order_by(AiMessage.created_at.asc())
        )
        return [_to_message_response(row) for row in result.scalars().all()]

    async def get_context(
        self, session_id: uuid.UUID, user_id: str, *, limit: int = 20
    ) -> ContextResponse:
        await self._sessions.get_session_row(session_id, user_id)
        result = await self._session.execute(
            select(AiMessage)
            .where(AiMessage.session_id == session_id)
            .order_by(AiMessage.created_at.desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
        rows.reverse()
        return ContextResponse(
            session_id=session_id,
            messages=[_to_message_response(row) for row in rows],
        )

    async def _resolve_session(
        self, session_id: uuid.UUID, payload: AppendMessagesRequest
    ) -> AiSession:
        result = await self._session.execute(
            select(AiSession).where(
                AiSession.id == session_id,
                AiSession.user_id == payload.user_id,
                AiSession.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            return row

        create_payload = SessionCreate(
            id=session_id,
            product_id=payload.product_id,
            agent_type=payload.agent_type,
            channel=payload.channel,
        )
        await self._sessions.create_session(payload.user_id, create_payload)
        result = await self._session.execute(
            select(AiSession).where(AiSession.id == session_id)
        )
        created = result.scalar_one()
        return created

    @staticmethod
    def _maybe_set_title(
        ai_session: AiSession, messages: list[MessageAppendItem]
    ) -> None:
        if ai_session.title not in (DEFAULT_TITLE, ""):
            return
        for item in messages:
            if item.role == MessageRole.user and item.content.strip():
                ai_session.title = title_from_first_message(item.content)
                return

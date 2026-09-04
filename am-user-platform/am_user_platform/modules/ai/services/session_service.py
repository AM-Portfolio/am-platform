"""Session CRUD for the ai module."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from am_platform_common import NotFoundError

from am_user_platform.core.log_utils import get_logger
from am_user_platform.modules.ai.models.db import AiSession
from am_user_platform.modules.ai.schemas.session import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
)

logger = get_logger("session_service")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_session_response(row: AiSession) -> SessionResponse:
    return SessionResponse.model_validate(row)


class SessionService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(
        self,
        user_id: str,
        payload: SessionCreate,
    ) -> SessionResponse:
        row = AiSession(
            id=payload.id or uuid.uuid4(),
            user_id=user_id,
            product_id=payload.product_id,
            agent_type=payload.agent_type,
            channel=payload.channel,
            title=payload.title or "New chat",
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        logger.info(
            "session created",
            extra={
                "session_id": str(row.id),
                "user_id": user_id,
                "agent_type": row.agent_type,
            },
        )
        return _to_session_response(row)

    async def list_sessions(
        self,
        user_id: str,
        *,
        product_id: str | None = None,
        agent_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SessionListResponse:
        filters = [
            AiSession.user_id == user_id,
            AiSession.deleted_at.is_(None),
        ]
        if product_id:
            filters.append(AiSession.product_id == product_id)
        if agent_type:
            filters.append(AiSession.agent_type == agent_type)

        total_result = await self._session.execute(
            select(func.count()).select_from(AiSession).where(*filters)
        )
        total = int(total_result.scalar_one())

        result = await self._session.execute(
            select(AiSession)
            .where(*filters)
            .order_by(AiSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [_to_session_response(row) for row in result.scalars().all()]
        return SessionListResponse(
            items=items, total=total, limit=limit, offset=offset
        )

    async def get_session(
        self, session_id: uuid.UUID, user_id: str
    ) -> SessionResponse:
        row = await self._get_owned_session(session_id, user_id)
        return _to_session_response(row)

    async def get_session_row(
        self, session_id: uuid.UUID, user_id: str
    ) -> AiSession:
        return await self._get_owned_session(session_id, user_id)

    async def update_title(
        self, session_id: uuid.UUID, user_id: str, title: str
    ) -> SessionResponse:
        row = await self._get_owned_session(session_id, user_id)
        row.title = title.strip() or row.title
        row.updated_at = _utcnow()
        await self._session.flush()
        await self._session.refresh(row)
        return _to_session_response(row)

    async def soft_delete(self, session_id: uuid.UUID, user_id: str) -> None:
        row = await self._get_owned_session(session_id, user_id)
        row.deleted_at = _utcnow()
        row.updated_at = _utcnow()
        await self._session.flush()

    async def purge_user_data(self, user_id: str) -> int:
        result = await self._session.execute(
            select(AiSession).where(AiSession.user_id == user_id)
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        logger.info(
            "purged user ai data",
            extra={"user_id": user_id, "sessions_deleted": len(rows)},
        )
        return len(rows)

    async def _get_owned_session(
        self, session_id: uuid.UUID, user_id: str
    ) -> AiSession:
        result = await self._session.execute(
            select(AiSession).where(
                AiSession.id == session_id,
                AiSession.user_id == user_id,
                AiSession.deleted_at.is_(None),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise NotFoundError(
                "Session not found",
                error_code="SESSION_NOT_FOUND",
                details={"session_id": str(session_id)},
            )
        return row

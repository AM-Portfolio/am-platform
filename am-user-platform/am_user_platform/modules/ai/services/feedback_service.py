"""Feedback persistence for the ai module."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from am_platform_common import NotFoundError

from am_user_platform.core.log_utils import get_logger
from am_user_platform.modules.ai.models.db import AiFeedback, AiMessage
from am_user_platform.modules.ai.schemas.feedback import FeedbackCreate, FeedbackResponse
from am_user_platform.modules.ai.services.session_service import SessionService

logger = get_logger("feedback_service")


class FeedbackService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._sessions = SessionService(session)

    async def create_feedback(
        self, user_id: str, payload: FeedbackCreate
    ) -> FeedbackResponse:
        await self._sessions.get_session_row(payload.session_id, user_id)
        if payload.message_id is not None:
            message = await self._session.get(AiMessage, payload.message_id)
            if message is None or message.session_id != payload.session_id:
                raise NotFoundError(
                    "Message not found in session",
                    error_code="MESSAGE_NOT_FOUND",
                    details={"message_id": str(payload.message_id)},
                )

        row = AiFeedback(
            user_id=user_id,
            session_id=payload.session_id,
            message_id=payload.message_id,
            agent_type=payload.agent_type,
            rating=payload.rating,
            comment=payload.comment,
            trace_id=payload.trace_id,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        logger.info(
            "feedback created",
            extra={
                "user_id": user_id,
                "session_id": str(payload.session_id),
                "rating": payload.rating,
            },
        )
        return FeedbackResponse.model_validate(row)

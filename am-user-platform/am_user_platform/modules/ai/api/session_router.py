"""User-facing AI APIs — JWT via gateway."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_auth_context

from am_user_platform.deps import (
    get_feedback_service,
    get_message_service,
    get_session_service,
)
from am_user_platform.modules.ai.schemas.feedback import FeedbackCreate, FeedbackResponse
from am_user_platform.modules.ai.schemas.session import (
    SessionCreate,
    SessionDetailResponse,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
)
from am_user_platform.modules.ai.services.feedback_service import FeedbackService
from am_user_platform.modules.ai.services.message_service import MessageService
from am_user_platform.modules.ai.services.session_service import SessionService

UserAuth = require_auth_context()

router = APIRouter(prefix="/v1/user-platform/ai", tags=["ai-sessions"])


@router.get("/sessions", response_model=APIResponse[SessionListResponse])
async def list_sessions(
    product_id: str | None = Query(default=None),
    agent_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(UserAuth),
    service: SessionService = Depends(get_session_service),
):
    data = await service.list_sessions(
        context.subject,
        product_id=product_id,
        agent_type=agent_type,
        limit=limit,
        offset=offset,
    )
    return APIResponse(data=data)


@router.post(
    "/sessions",
    response_model=APIResponse[SessionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_session(
    payload: SessionCreate,
    context: AuthContext = Depends(UserAuth),
    service: SessionService = Depends(get_session_service),
):
    data = await service.create_session(context.subject, payload)
    return APIResponse(data=data)


@router.get("/sessions/{session_id}", response_model=APIResponse[SessionDetailResponse])
async def get_session(
    session_id: uuid.UUID,
    context: AuthContext = Depends(UserAuth),
    session_service: SessionService = Depends(get_session_service),
    message_service: MessageService = Depends(get_message_service),
):
    session = await session_service.get_session(session_id, context.subject)
    messages = await message_service.get_messages(session_id, context.subject)
    return APIResponse(
        data=SessionDetailResponse(session=session, messages=messages)
    )


@router.patch("/sessions/{session_id}", response_model=APIResponse[SessionResponse])
async def update_session(
    session_id: uuid.UUID,
    payload: SessionUpdate,
    context: AuthContext = Depends(UserAuth),
    service: SessionService = Depends(get_session_service),
):
    data = await service.update_title(session_id, context.subject, payload.title)
    return APIResponse(data=data)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_session(
    session_id: uuid.UUID,
    context: AuthContext = Depends(UserAuth),
    service: SessionService = Depends(get_session_service),
):
    await service.soft_delete(session_id, context.subject)


@router.post(
    "/feedback",
    response_model=APIResponse[FeedbackResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_feedback(
    payload: FeedbackCreate,
    context: AuthContext = Depends(UserAuth),
    service: FeedbackService = Depends(get_feedback_service),
):
    data = await service.create_feedback(context.subject, payload)
    return APIResponse(data=data)

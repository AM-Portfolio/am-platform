"""Internal AI APIs — service token (agents, gateway)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_service_account

from am_user_platform.deps import get_message_service, get_session_service
from am_user_platform.modules.ai.schemas.message import (
    AppendMessagesRequest,
    ContextResponse,
    MessageResponse,
)
from am_user_platform.modules.ai.services.message_service import MessageService
from am_user_platform.modules.ai.services.session_service import SessionService

INTERNAL_CLIENTS = {
    "am-gateway-client",
    "am-fin-agent",
    "am-fin-agent-service",
    "am-tool-agent",
    "am-qa-agent",
    "am-support-agent",
}

ServiceAuth = require_service_account(allowed_client_ids=INTERNAL_CLIENTS)

router = APIRouter(prefix="/internal/ai", tags=["internal-ai"])


@router.get(
    "/sessions/{session_id}/context",
    response_model=APIResponse[ContextResponse],
)
async def get_session_context(
    session_id: uuid.UUID,
    user_id: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
    _: AuthContext = Depends(ServiceAuth),
    service: MessageService = Depends(get_message_service),
):
    data = await service.get_context(session_id, user_id, limit=limit)
    return APIResponse(data=data)


@router.post(
    "/sessions/{session_id}/messages",
    response_model=APIResponse[list[MessageResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def append_session_messages(
    session_id: uuid.UUID,
    payload: AppendMessagesRequest,
    _: AuthContext = Depends(ServiceAuth),
    service: MessageService = Depends(get_message_service),
):
    data = await service.append_messages(session_id, payload)
    return APIResponse(data=data)


@router.delete(
    "/users/{user_id}/data",
    response_model=APIResponse[dict[str, int]],
)
async def purge_user_ai_data(
    user_id: str,
    _: AuthContext = Depends(ServiceAuth),
    service: SessionService = Depends(get_session_service),
):
    deleted = await service.purge_user_data(user_id)
    return APIResponse(data={"sessions_deleted": deleted})

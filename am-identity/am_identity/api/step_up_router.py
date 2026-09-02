from __future__ import annotations

from fastapi import APIRouter, Depends

from am_identity.schemas.session import StepUpResponse
from am_identity.services.step_up_service import step_up_service
from am_platform_security import AuthContext, require_auth_context

router = APIRouter(prefix="/auth", tags=["step-up"])


@router.post("/step-up", response_model=StepUpResponse)
async def step_up(
    context: AuthContext = Depends(require_auth_context()),
) -> StepUpResponse:
    record = step_up_service.issue(context.subject)
    return StepUpResponse(step_up_token=record.token, expires_at=record.expires_at)

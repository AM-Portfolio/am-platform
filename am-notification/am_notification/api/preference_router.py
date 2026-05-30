from fastapi import APIRouter, Depends

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_auth_context

from am_notification.deps import get_preference_service
from am_notification.schemas.notification import PreferenceUpdate
from am_notification.services.preference_service import PreferenceService

router = APIRouter(prefix="/notifications/preferences", tags=["preferences"])


@router.get("", response_model=APIResponse[dict])
async def get_preferences(
    context: AuthContext = Depends(require_auth_context()),
    service: PreferenceService = Depends(get_preference_service),
):
    data = await service.get_preferences(context.subject)
    return APIResponse(data=data)


@router.put("", response_model=APIResponse[dict])
async def update_preferences(
    payload: PreferenceUpdate,
    context: AuthContext = Depends(require_auth_context()),
    service: PreferenceService = Depends(get_preference_service),
):
    data = await service.update_preferences(
        context.subject, payload.model_dump(exclude_none=True)
    )
    return APIResponse(data=data)

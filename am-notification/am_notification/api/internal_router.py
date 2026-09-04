from fastapi import APIRouter, Depends, status

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_service_account

from am_notification.deps import get_notification_service
from am_notification.schemas.notification import NotificationCommand
from am_notification.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications/internal", tags=["internal"])


@router.post(
    "/send", response_model=APIResponse[dict], status_code=status.HTTP_202_ACCEPTED
)
async def internal_send(
    payload: NotificationCommand,
    _context: AuthContext = Depends(require_service_account()),
    service: NotificationService = Depends(get_notification_service),
):
    result = await service.send_command(payload.model_dump())
    return APIResponse(data=result)

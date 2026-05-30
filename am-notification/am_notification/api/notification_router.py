from fastapi import APIRouter, Depends, Query

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_auth_context

from am_notification.deps import get_notification_service
from am_notification.schemas.notification import MarkReadRequest
from am_notification.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/me", response_model=APIResponse[list[dict]])
async def list_my_notifications(
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    context: AuthContext = Depends(require_auth_context()),
    service: NotificationService = Depends(get_notification_service),
):
    data = await service.list_inbox(
        context.subject, page=page, page_size=page_size, unread_only=unread_only
    )
    return APIResponse(data=data)


@router.get("/me/unread-count", response_model=APIResponse[dict])
async def unread_count(
    context: AuthContext = Depends(require_auth_context()),
    service: NotificationService = Depends(get_notification_service),
):
    count = await service.unread_count(context.subject)
    return APIResponse(data={"count": count})


@router.patch("/{notification_id}/read", response_model=APIResponse[dict])
async def mark_notification_read(
    notification_id: str,
    context: AuthContext = Depends(require_auth_context()),
    service: NotificationService = Depends(get_notification_service),
):
    await service.mark_read(context.subject, [notification_id])
    return APIResponse(data={"notification_id": notification_id, "read": True})


@router.patch("/read-all", response_model=APIResponse[dict])
async def mark_all_read(
    context: AuthContext = Depends(require_auth_context()),
    service: NotificationService = Depends(get_notification_service),
):
    await service.mark_all_read(context.subject)
    return APIResponse(data={"read_all": True})


@router.post("/mark-read", response_model=APIResponse[dict])
async def mark_read_batch(
    payload: MarkReadRequest,
    context: AuthContext = Depends(require_auth_context()),
    service: NotificationService = Depends(get_notification_service),
):
    await service.mark_read(context.subject, payload.notification_ids)
    return APIResponse(data={"count": len(payload.notification_ids)})

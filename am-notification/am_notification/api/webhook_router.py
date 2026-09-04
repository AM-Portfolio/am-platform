from typing import Any

from fastapi import APIRouter, Request

from am_platform_common import APIResponse

from am_notification.core.log_utils import get_logger
from am_notification.core.database import get_database

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = get_logger("webhook.novu")


@router.post("/novu", response_model=APIResponse[dict])
async def novu_webhook(request: Request) -> APIResponse[dict]:
    payload: dict[str, Any] = await request.json()
    event_type = payload.get("type") or payload.get("event")
    message_id = payload.get("messageId") or payload.get("message_id")
    subscriber_id = payload.get("subscriberId") or payload.get("subscriber_id")
    status = payload.get("status") or payload.get("deliveryState")

    if message_id and subscriber_id:
        db = get_database()
        await db.notification_delivery_attempts.update_many(
            {"provider_message_id": message_id, "recipient_user_id": subscriber_id},
            {"$set": {"webhook_status": status, "webhook_event": event_type}},
        )
        logger.info(
            "Novu webhook processed",
            extra={
                "message_id": message_id,
                "subscriber_id": subscriber_id,
                "status": status,
            },
        )

    return APIResponse(data={"received": True})

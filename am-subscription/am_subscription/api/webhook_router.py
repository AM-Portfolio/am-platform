import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request

from am_platform_common import APIResponse

from am_subscription.deps import get_event_publisher
from am_subscription.services.event_publisher import EventPublisher

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/provider", response_model=APIResponse[dict[str, Any]])
async def provider_webhook(
    request: Request,
    events: EventPublisher = Depends(get_event_publisher),
    x_lago_signature: str | None = Header(default=None),
):
    """Translate billing provider webhooks into canonical platform events."""
    body = await request.json()
    webhook_type = body.get("webhook_type") or body.get("object_type") or "unknown"
    user_id = body.get("customer", {}).get("external_id") or body.get(
        "subscription", {}
    ).get("external_customer_id")
    correlation_id = body.get("webhook_id") or EventPublisher.new_correlation_id()

    event_map = {
        "subscription.started": "am.subscription.created.v1",
        "subscription.terminated": "am.subscription.changed.v1",
        "invoice.payment_failure": "am.subscription.suspended.v1",
    }
    event_type = event_map.get(webhook_type, f"am.billing.webhook.{webhook_type}")

    await events.publish(
        event_type,
        tenant_id=user_id or "unknown",
        user_id=(
            user_id.replace("am-user-", "")
            if user_id and user_id.startswith("am-user-")
            else user_id
        ),
        correlation_id=correlation_id,
        idempotency_key=correlation_id,
        payload={"webhook_type": webhook_type, "raw": body},
    )

    logger.info(
        "provider_webhook_received",
        extra={"webhook_type": webhook_type, "signature": bool(x_lago_signature)},
    )
    return APIResponse(data={"accepted": True, "webhook_type": webhook_type})

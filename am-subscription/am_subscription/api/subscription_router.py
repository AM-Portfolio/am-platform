from uuid import UUID

from fastapi import APIRouter, Depends, status

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_auth_context

from am_subscription.core.log_utils import get_logger
from am_subscription.deps import get_subscription_service
from am_subscription.schemas.subscription import (
    CreateSubscriptionRequest,
    StateChangeRequest,
    SubscriptionDTO,
    UpgradeSubscriptionRequest,
    UsageHistoryResponse,
)
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.subscription_service import SubscriptionService

logger = get_logger("api.subscriptions")
router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


def _correlation_id() -> str:
    return EventPublisher.new_correlation_id()


@router.post(
    "", response_model=APIResponse[SubscriptionDTO], status_code=status.HTTP_201_CREATED
)
async def create_subscription(
    payload: CreateSubscriptionRequest,
    context: AuthContext = Depends(require_auth_context()),
    service: SubscriptionService = Depends(get_subscription_service),
):
    logger.info(
        "POST /subscriptions",
        extra={"user_id": context.subject, "plan_code": payload.plan_code},
    )
    data = await service.get_or_create(
        context.subject,
        payload,
        actor=context.subject,
        correlation_id=_correlation_id(),
    )
    return APIResponse(data=data)


@router.get("/me", response_model=APIResponse[SubscriptionDTO])
async def get_my_subscription(
    context: AuthContext = Depends(require_auth_context()),
    service: SubscriptionService = Depends(get_subscription_service),
):
    existing = await service.get_by_user(context.subject)
    if not existing:
        data = await service.get_or_create(
            context.subject,
            CreateSubscriptionRequest(tenant_id=context.claims.get("tenant_id")),
            actor=context.subject,
            correlation_id=_correlation_id(),
        )
        return APIResponse(data=data)
    return APIResponse(data=await service.to_dto(existing))


@router.patch("/{subscription_id}/cancel", response_model=APIResponse[SubscriptionDTO])
async def cancel_subscription(
    subscription_id: UUID,
    payload: StateChangeRequest,
    context: AuthContext = Depends(require_auth_context()),
    service: SubscriptionService = Depends(get_subscription_service),
):
    data = await service.cancel(
        subscription_id,
        context.subject,
        actor=context.subject,
        reason=payload.reason,
        correlation_id=_correlation_id(),
    )
    return APIResponse(data=data)


@router.patch("/{subscription_id}/pause", response_model=APIResponse[SubscriptionDTO])
async def pause_subscription(
    subscription_id: UUID,
    payload: StateChangeRequest,
    context: AuthContext = Depends(require_auth_context()),
    service: SubscriptionService = Depends(get_subscription_service),
):
    data = await service.pause(
        subscription_id,
        context.subject,
        actor=context.subject,
        reason=payload.reason,
        correlation_id=_correlation_id(),
    )
    return APIResponse(data=data)


@router.patch("/{subscription_id}/resume", response_model=APIResponse[SubscriptionDTO])
async def resume_subscription(
    subscription_id: UUID,
    payload: StateChangeRequest,
    context: AuthContext = Depends(require_auth_context()),
    service: SubscriptionService = Depends(get_subscription_service),
):
    data = await service.resume(
        subscription_id,
        context.subject,
        actor=context.subject,
        reason=payload.reason,
        correlation_id=_correlation_id(),
    )
    return APIResponse(data=data)


@router.patch("/{subscription_id}/upgrade", response_model=APIResponse[SubscriptionDTO])
async def upgrade_subscription(
    subscription_id: UUID,
    payload: UpgradeSubscriptionRequest,
    context: AuthContext = Depends(require_auth_context()),
    service: SubscriptionService = Depends(get_subscription_service),
):
    data = await service.upgrade(
        subscription_id,
        context.subject,
        payload,
        actor=context.subject,
        correlation_id=_correlation_id(),
    )
    return APIResponse(data=data)


@router.get("/usage/history", response_model=APIResponse[UsageHistoryResponse])
async def usage_history(
    context: AuthContext = Depends(require_auth_context()),
    service: SubscriptionService = Depends(get_subscription_service),
):
    data = await service.usage_history(context.subject)
    return APIResponse(data=data)

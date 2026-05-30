from fastapi import APIRouter, Depends, Query

from am_platform_common import APIResponse
from am_subscription.deps import get_subscription_service
from am_subscription.schemas.subscription import PlanDTO
from am_subscription.services.subscription_service import SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["plans"])


@router.get("/plans", response_model=APIResponse[list[PlanDTO]])
async def list_plans(
    interval: str | None = Query(default=None, description="monthly or yearly"),
    service: SubscriptionService = Depends(get_subscription_service),
):
    plans = await service.list_plans(interval=interval)
    return APIResponse(data=plans)

from fastapi import APIRouter, Depends

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_service_account

from am_subscription.deps import (
    get_entitlement_service,
    get_metering_service,
    get_subscription_service,
)
from am_subscription.schemas.entitlement import (
    EntitlementCheckRequest,
    EntitlementCheckResponse,
    EntitlementsResponse,
)
from am_subscription.schemas.meter import MeterRequest, MeterResponse
from am_subscription.schemas.subscription import CreateSubscriptionRequest, SubscriptionDTO
from am_subscription.services.entitlement_service import EntitlementService, MeteringService
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.subscription_service import SubscriptionService

INTERNAL_CLIENTS = {
    "am-gateway-client",
    "am-portfolio-service",
    "am-market-service",
    "am-market-data-service",
    "am-doc-intelligence-service",
    "am-analysis-service",
    "am-parser-service",
    "am-market-parser-service",
}

router = APIRouter(prefix="/subscriptions/internal", tags=["internal"])


@router.get("/entitlements/{user_id}", response_model=APIResponse[EntitlementsResponse])
async def get_user_entitlements(
    user_id: str,
    _: AuthContext = Depends(require_service_account(allowed_client_ids=INTERNAL_CLIENTS)),
    service: EntitlementService = Depends(get_entitlement_service),
):
    return APIResponse(data=await service.get_entitlements(user_id))


@router.post("/check", response_model=APIResponse[EntitlementCheckResponse])
async def check_entitlement(
    payload: EntitlementCheckRequest,
    _: AuthContext = Depends(require_service_account(allowed_client_ids=INTERNAL_CLIENTS)),
    service: EntitlementService = Depends(get_entitlement_service),
):
    return APIResponse(data=await service.check(payload))


@router.post("/meter", response_model=APIResponse[MeterResponse])
async def record_meter(
    payload: MeterRequest,
    _: AuthContext = Depends(require_service_account(allowed_client_ids=INTERNAL_CLIENTS)),
    service: MeteringService = Depends(get_metering_service),
):
    return APIResponse(data=await service.record(payload))


@router.post("/bootstrap/{user_id}", response_model=APIResponse[SubscriptionDTO])
async def bootstrap_subscription(
    user_id: str,
    plan_code: str | None = None,
    _: AuthContext = Depends(require_service_account(allowed_client_ids=INTERNAL_CLIENTS)),
    service: SubscriptionService = Depends(get_subscription_service),
):
    """Ensure a user has a subscription (defaults to free tier)."""
    data = await service.get_or_create(
        user_id,
        CreateSubscriptionRequest(plan_code=plan_code),
        actor="system",
        correlation_id=EventPublisher.new_correlation_id(),
    )
    return APIResponse(data=data)

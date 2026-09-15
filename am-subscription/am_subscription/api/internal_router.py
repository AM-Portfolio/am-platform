from uuid import UUID
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_service_account

from am_subscription.deps import (
    get_entitlement_service,
    get_grant_service,
    get_metering_service,
    get_referral_service,
    get_subscription_service,
)
from am_subscription.schemas.entitlement import (
    EntitlementCheckRequest,
    EntitlementCheckResponse,
    EntitlementsResponse,
)
from am_subscription.schemas.meter import MeterRequest, MeterResponse
from am_subscription.schemas.referral import (
    AttributionResponse,
    AttributeReferralRequest,
    QualifyReferralRequest,
)
from am_subscription.schemas.subscription import (
    CreateSubscriptionRequest,
    SubscriptionDTO,
)
from am_subscription.services.entitlement_service import (
    EntitlementService,
    MeteringService,
)
from am_subscription.services.event_publisher import EventPublisher
from am_subscription.services.grant_service import GrantService
from am_subscription.services.referral_service import ReferralService
from am_subscription.services.subscription_service import SubscriptionService

INTERNAL_CLIENTS = {
    "am-gateway-client",
    "am-identity-service",
    "am-fin-agent-service",
    "am-portfolio-service",
    "am-market-service",
    "am-market-data-service",
    "am-doc-intelligence-service",
    "am-analysis-service",
    "am-parser-service",
    "am-market-parser-service",
}

router = APIRouter(prefix="/subscriptions/internal", tags=["internal"])


class ProDaysGrantRequest(BaseModel):
    user_id: str
    days: int = Field(default=30, ge=1, le=365)
    plan_code: str = "am_pro"
    reason: str = Field(description="trial | referral")
    idempotency_key: str
    email: str | None = None
    attribution_id: str | None = None


@router.get("/entitlements/{user_id}", response_model=APIResponse[EntitlementsResponse])
async def get_user_entitlements(
    user_id: str,
    _: AuthContext = Depends(
        require_service_account(allowed_client_ids=INTERNAL_CLIENTS)
    ),
    service: EntitlementService = Depends(get_entitlement_service),
):
    return APIResponse(data=await service.get_entitlements(user_id))


@router.post("/check", response_model=APIResponse[EntitlementCheckResponse])
async def check_entitlement(
    payload: EntitlementCheckRequest,
    _: AuthContext = Depends(
        require_service_account(allowed_client_ids=INTERNAL_CLIENTS)
    ),
    service: EntitlementService = Depends(get_entitlement_service),
):
    return APIResponse(data=await service.check(payload))


@router.post("/meter", response_model=APIResponse[MeterResponse])
async def record_meter(
    payload: MeterRequest,
    _: AuthContext = Depends(
        require_service_account(allowed_client_ids=INTERNAL_CLIENTS)
    ),
    service: MeteringService = Depends(get_metering_service),
):
    return APIResponse(data=await service.record(payload))


@router.post("/bootstrap/{user_id}", response_model=APIResponse[SubscriptionDTO])
async def bootstrap_subscription(
    user_id: str,
    plan_code: str | None = None,
    _: AuthContext = Depends(
        require_service_account(allowed_client_ids=INTERNAL_CLIENTS)
    ),
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


def _attribution_response(row, *, created: bool = False) -> AttributionResponse:
    if row is None:
        return AttributionResponse(created=False)
    return AttributionResponse(
        id=str(row.id),
        referee_user_id=row.referee_user_id,
        referrer_user_id=row.referrer_user_id,
        code=row.code,
        status=row.status.value,
        reject_reason=row.reject_reason,
        created=created,
    )


@router.post("/referrals/attribute", response_model=APIResponse[AttributionResponse])
async def attribute_referral(
    payload: AttributeReferralRequest,
    _: AuthContext = Depends(
        require_service_account(allowed_client_ids=INTERNAL_CLIENTS)
    ),
    service: ReferralService = Depends(get_referral_service),
):
    row = await service.attribute(
        referee_user_id=payload.referee_user_id,
        email=payload.email,
        referral_code=payload.referral_code,
        device_id=payload.device_id,
        event_id=payload.event_id,
        idempotency_key=payload.idempotency_key,
    )
    return APIResponse(data=_attribution_response(row, created=row is not None))


@router.post("/referrals/qualify", response_model=APIResponse[AttributionResponse])
async def qualify_referral(
    payload: QualifyReferralRequest,
    _: AuthContext = Depends(
        require_service_account(allowed_client_ids=INTERNAL_CLIENTS)
    ),
    service: ReferralService = Depends(get_referral_service),
):
    attribution_id = UUID(payload.attribution_id) if payload.attribution_id else None
    row = await service.qualify(
        referee_user_id=payload.referee_user_id,
        attribution_id=attribution_id,
    )
    return APIResponse(data=_attribution_response(row))


@router.post("/grants/pro-days", response_model=APIResponse[dict[str, Any]])
async def grant_pro_days(
    payload: ProDaysGrantRequest,
    _: AuthContext = Depends(
        require_service_account(allowed_client_ids=INTERNAL_CLIENTS)
    ),
    service: GrantService = Depends(get_grant_service),
):
    """Unified timed Pro grant — service JWT only (user tokens rejected)."""
    data = await service.grant_pro_days(
        user_id=payload.user_id,
        days=payload.days,
        plan_code=payload.plan_code,
        reason=payload.reason,
        idempotency_key=payload.idempotency_key,
        email=payload.email,
        attribution_id=payload.attribution_id,
    )
    return APIResponse(data=data)

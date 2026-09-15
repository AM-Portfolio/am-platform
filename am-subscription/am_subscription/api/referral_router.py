from fastapi import APIRouter, Depends, Query

from am_platform_common import APIResponse
from am_platform_security import AuthContext, require_auth_context

from am_subscription.deps import get_referral_service
from am_subscription.schemas.referral import ReferralHistoryItem, ReferralMeResponse
from am_subscription.services.referral_service import ReferralService

router = APIRouter(prefix="/subscriptions/referrals", tags=["referrals"])


@router.get("/me", response_model=APIResponse[ReferralMeResponse])
async def get_my_referral(
    context: AuthContext = Depends(require_auth_context()),
    service: ReferralService = Depends(get_referral_service),
):
    email = context.claims.get("email") if context.claims else None
    data = await service.get_my_summary(context.subject, email=email)
    return APIResponse(data=ReferralMeResponse(**data))


@router.get("/me/history", response_model=APIResponse[list[ReferralHistoryItem]])
async def get_my_referral_history(
    limit: int = Query(default=50, ge=1, le=200),
    context: AuthContext = Depends(require_auth_context()),
    service: ReferralService = Depends(get_referral_service),
):
    rows = await service.get_history(context.subject, limit=limit)
    return APIResponse(data=[ReferralHistoryItem(**row) for row in rows])

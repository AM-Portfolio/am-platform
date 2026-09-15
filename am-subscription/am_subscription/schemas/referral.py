from pydantic import BaseModel, Field


class ReferralMeResponse(BaseModel):
    code: str
    share_url: str
    status: str
    qualified_count: int
    active_count: int
    remaining: int
    lifetime_cap: int
    daily_used: int
    daily_cap: int
    daily_remaining: int
    joined: dict | None = None


class ReferralHistoryItem(BaseModel):
    id: str
    status: str
    reject_reason: str | None = None
    created_at: str | None = None
    qualified_at: str | None = None
    code_hint: str | None = None


class AttributeReferralRequest(BaseModel):
    referee_user_id: str
    email: str | None = None
    referral_code: str | None = None
    device_id: str | None = None
    event_id: str | None = None
    idempotency_key: str | None = None


class QualifyReferralRequest(BaseModel):
    referee_user_id: str | None = None
    attribution_id: str | None = Field(
        default=None, description="UUID of pending attribution"
    )


class AttributionResponse(BaseModel):
    id: str | None = None
    referee_user_id: str | None = None
    referrer_user_id: str | None = None
    code: str | None = None
    status: str | None = None
    reject_reason: str | None = None
    created: bool = False

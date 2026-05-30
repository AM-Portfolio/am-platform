from am_platform_common import BaseDTO


class EntitlementCheckRequest(BaseDTO):
    user_id: str
    tenant_id: str | None = None
    feature: str
    action: str
    quantity: int = 1
    idempotency_key: str


class EntitlementCheckResponse(BaseDTO):
    allowed: bool
    reason: str | None = None
    plan_code: str | None = None
    feature: str
    action: str
    remaining: int | None = None


class EntitlementsResponse(BaseDTO):
    user_id: str
    plan_code: str
    state: str
    entitlements: dict[str, bool]
    limits: dict[str, int]
    usage: dict[str, int]

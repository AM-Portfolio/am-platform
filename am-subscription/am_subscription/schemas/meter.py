from typing import Any

from am_platform_common import BaseDTO


class MeterRequest(BaseDTO):
    user_id: str
    metric_code: str
    quantity: int = 1
    idempotency_key: str
    properties: dict[str, Any] | None = None


class MeterResponse(BaseDTO):
    accepted: bool
    duplicate: bool = False
    metric_code: str
    quantity: int
    synced: bool = False

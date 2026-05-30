from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_serializer

T = TypeVar("T")

class BaseDTO(BaseModel):
    """Base Pydantic model configuration for all DTOs."""
    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }


class APIResponse(BaseDTO, Generic[T]):
    """Standard success envelope for API responses returning a single item."""
    data: T
    meta: Dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseDTO, Generic[T]):
    """Standard response envelope for paginated lists of items."""
    items: List[T]
    total: int
    page: int
    size: int
    pages: int
    meta: Dict[str, Any] = Field(default_factory=dict)


class APIErrorResponse(BaseDTO):
    """Standard error response structure returned on API exceptions."""
    error_code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class EventEnvelope(BaseDTO, Generic[T]):
    """Canonical event envelope for all Kafka events in the ecosystem."""
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    event_version: int = 1
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    producer: str
    tenant_id: str
    user_id: Optional[str] = None
    correlation_id: str
    idempotency_key: str
    payload: T

    @field_serializer("occurred_at")
    def serialize_datetime(self, dt: datetime, _info: Any) -> str:
        return dt.isoformat()

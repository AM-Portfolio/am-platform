from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scope: str = Field(default="ai.read", pattern=r"^ai\.read$")


class ApiKeyResponse(BaseModel):
    id: UUID
    key_id: str
    key_prefix: str
    name: str
    scope: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


class ApiKeyCreateResponse(ApiKeyResponse):
    secret: str


class ApiKeyExchangeRequest(BaseModel):
    key_id: str = Field(min_length=1, max_length=100)
    secret: str = Field(min_length=1, max_length=512)

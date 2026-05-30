from typing import Any

from pydantic import BaseModel, Field


class AuthContext(BaseModel):
    subject: str = Field(..., description="User/service subject (`sub`)")
    client_id: str | None = Field(default=None, description="Client identifier from `azp` or `client_id`")
    token_type: str = Field(default="user", description="user or service")
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    claims: dict[str, Any] = Field(default_factory=dict)
    access_token: str = Field(..., description="Raw bearer token for downstream OIDC calls")

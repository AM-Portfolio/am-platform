from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class SecurityEventResponse(BaseModel):
    event_id: str
    type: Literal["new_device_login"]
    session_id: str | None
    device_label: str | None
    geo_city: str | None
    geo_country: str | None
    created_at: float
    acknowledged: bool


class LoginSessionResponse(BaseModel):
    session_id: str
    browser: str | None
    os: str | None
    client_type: str
    geo_city: str | None
    geo_country: str | None
    ip_masked: str | None
    machine_label: str | None
    created_at: float
    last_active_at: float
    current: bool = False

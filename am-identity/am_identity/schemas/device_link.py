from __future__ import annotations

from pydantic import BaseModel, Field


class DeviceLinkStartRequest(BaseModel):
    client: str = "web"
    redirect_hint: str
    code_challenge: str
    browser: str | None = None
    os: str | None = None


class DeviceLinkStartResponse(BaseModel):
    device_link_id: str
    qr_payload: dict[str, str | int]
    confirmation_code: str
    expires_at: float
    poll_interval_ms: int = 2000


class DeviceLinkUserResponse(BaseModel):
    sub: str
    email: str | None = None
    preferred_username: str | None = None


class WebSessionTokensResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int | None = None


class DeviceLinkStatusResponse(BaseModel):
    status: str
    user: DeviceLinkUserResponse | None = None
    tokens: WebSessionTokensResponse | None = None


class DeviceLinkPreviewResponse(BaseModel):
    host: str
    confirmation_code: str
    browser: str | None
    os: str | None
    geo_city: str | None
    geo_country: str | None
    ip_masked: str | None
    is_new_device: bool
    requested_at: float


class DeviceLinkApproveRequest(BaseModel):
    device_name: str | None = None
    confirmation_code: str
    machine_label: str | None = None


class DeviceLinkApproveResponse(BaseModel):
    status: str


class DeviceLinkDenyRequest(BaseModel):
    reason: str | None = None

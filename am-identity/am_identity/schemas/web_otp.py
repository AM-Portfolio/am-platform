from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WebOtpSendRequest(BaseModel):
    channel: Literal["email", "sms"]
    destination: str


class WebOtpSendResponse(BaseModel):
    otp_session_id: str
    expires_at: float
    masked_destination: str


class WebOtpVerifyRequest(BaseModel):
    otp_session_id: str
    code: str = Field(min_length=4, max_length=8)


class WebOtpVerifyUserResponse(BaseModel):
    sub: str
    email: str | None = None
    preferred_username: str | None = None


class WebOtpVerifyResponse(BaseModel):
    user: WebOtpVerifyUserResponse

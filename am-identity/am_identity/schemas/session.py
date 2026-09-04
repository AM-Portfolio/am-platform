from __future__ import annotations

from pydantic import BaseModel


class BffMeResponse(BaseModel):
    sub: str
    email: str | None = None
    preferred_username: str | None = None
    given_name: str | None = None
    family_name: str | None = None


class StepUpResponse(BaseModel):
    step_up_token: str
    expires_at: float

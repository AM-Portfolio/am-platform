from typing import Any

from pydantic import BaseModel, EmailStr


class UserProfileResponse(BaseModel):
    sub: str
    email: EmailStr | None = None
    preferred_username: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    roles: list[str] = []
    settings: dict[str, Any] = {}
    deletion_pending: bool = False
    account_restored: bool = False

class AccountDeletionRequest(BaseModel):
    feedback: str

class UpdateUserSettingsRequest(BaseModel):
    settings: dict[str, Any]

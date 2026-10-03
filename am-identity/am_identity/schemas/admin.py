from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class RoleInfo(BaseModel):
    name: str
    description: str | None = None
    assignable: bool = True


class AdminUserSummary(BaseModel):
    id: str
    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool = True
    email_verified: bool = False
    roles: list[str] = Field(default_factory=list)


class CreateAdminUserRequest(BaseModel):
    email: EmailStr
    password: str | None = Field(default=None, min_length=8)
    first_name: str | None = None
    last_name: str | None = None
    enabled: bool = True
    send_verify_email: bool = True
    temporary_password: bool = False
    roles: list[str] = Field(default_factory=lambda: ["user"])
    create_mode: Literal["member", "viewer"] | None = None
    allow_elevated: bool = False


class UpdateAdminUserRequest(BaseModel):
    enabled: bool | None = None
    first_name: str | None = None
    last_name: str | None = None


class SetEnabledRequest(BaseModel):
    enabled: bool


class SetRolesRequest(BaseModel):
    roles: list[str]


class AddRolesRequest(BaseModel):
    roles: list[str]


class GroupInfo(BaseModel):
    id: str
    name: str
    path: str | None = None


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class AddUserGroupsRequest(BaseModel):
    group_ids: list[str] = Field(min_length=1)


class CustomRoleInfo(BaseModel):
    name: str
    description: str | None = None
    custom: bool = True
    storage: str | None = None


class CreateCustomRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class AuditEvent(BaseModel):
    at: datetime
    actor_id: str | None = None
    action: str
    target_user_id: str | None = None
    detail: str | None = None


class EffectiveAccessSummary(BaseModel):
    user_id: str
    roles: list[str] = Field(default_factory=list)
    groups: list[GroupInfo] = Field(default_factory=list)
    notes: str | None = None

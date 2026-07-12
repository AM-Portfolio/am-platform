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

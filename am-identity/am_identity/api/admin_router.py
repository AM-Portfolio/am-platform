from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from am_identity.deps import get_identity_provider
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.admin import (
    AddRolesRequest,
    AddUserGroupsRequest,
    AdminUserSummary,
    AuditEvent,
    CreateAdminUserRequest,
    CreateCustomRoleRequest,
    CreateGroupRequest,
    CustomRoleInfo,
    EffectiveAccessSummary,
    GroupInfo,
    RoleInfo,
    SetEnabledRequest,
    SetRolesRequest,
    UpdateAdminUserRequest,
)
from am_identity.services.admin_audit import append_audit_event, list_audit_events
from am_platform_security import AuthContext, require_any_roles

router = APIRouter(prefix="/admin", tags=["admin"])

_ASSIGNABLE_ROLES: dict[str, str] = {
    "user": "Standard portal user — own data only; no admin consoles",
    "viewer": "Read-only access across AM apps — no mutations",
    "ops": "Platform operator — Grafana/Argo/store UIs with registered IP",
    "admin": "Manage users and roles via Identity Admin",
    "super_admin": "Break-glass enterprise owner",
}
_HUMAN_ROLES = frozenset(_ASSIGNABLE_ROLES)
_CREATE_DEFAULT_ROLES = frozenset({"user", "viewer"})
_ELEVATED_CREATE_ROLES = frozenset({"ops", "admin", "super_admin"})
_ADMIN_GUARD = require_any_roles(["admin", "super_admin"])

# Fallback when Keycloak role APIs reject custom attributes.
_custom_roles_memory: dict[str, CustomRoleInfo] = {}


def _is_super_admin(context: AuthContext) -> bool:
    return "super_admin" in set(context.roles)


def _is_admin_actor(context: AuthContext) -> bool:
    roles = set(context.roles)
    return "admin" in roles or "super_admin" in roles


def _validate_role_names(roles: list[str], *, actor: AuthContext) -> list[str]:
    cleaned = list(dict.fromkeys(roles))
    for name in cleaned:
        if name == "service":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign service role via API",
            )
        if name not in _HUMAN_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown or non-assignable role: {name}",
            )
        if name == "super_admin" and not _is_super_admin(actor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super_admin may grant or revoke super_admin",
            )
    return cleaned


def _ensure_human_roles(roles: list[str]) -> list[str]:
    human = [r for r in roles if r in _HUMAN_ROLES]
    if not human:
        return ["user"]
    return human


def _resolve_create_roles(
    payload: CreateAdminUserRequest, *, actor: AuthContext
) -> list[str]:
    """Resolve roles for user creation.

    ``create_mode`` wins when set (member → user, viewer → viewer). Otherwise
    ``payload.roles`` is used (default ``["user"]``).

    ``ops``, ``admin``, and ``super_admin`` are rejected unless
    ``allow_elevated=True`` **and** the actor holds ``admin`` or ``super_admin``.
    """
    if payload.create_mode == "member":
        requested = ["user"]
    elif payload.create_mode == "viewer":
        requested = ["viewer"]
    else:
        requested = list(payload.roles) if payload.roles else ["user"]
    requested = list(dict.fromkeys(requested))
    elevated = [r for r in requested if r in _ELEVATED_CREATE_ROLES]
    if elevated:
        if not payload.allow_elevated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Elevated roles (ops, admin, super_admin) require "
                    "allow_elevated=true on create"
                ),
            )
        if not _is_admin_actor(actor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin or super_admin may create elevated users",
            )
        return _ensure_human_roles(_validate_role_names(requested, actor=actor))
    for name in requested:
        if name not in _CREATE_DEFAULT_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Role '{name}' is not allowed on create; use user/viewer "
                    "or set allow_elevated=true for platform roles"
                ),
            )
    return _ensure_human_roles(requested)


def _record_role_audit(
    *,
    action: str,
    actor: AuthContext,
    target_user_id: str,
    detail: str | None = None,
) -> None:
    append_audit_event(
        action=action,
        actor_id=actor.subject,
        target_user_id=target_user_id,
        detail=detail,
    )


@router.get("/roles", response_model=list[RoleInfo])
async def list_roles(
    _: AuthContext = Depends(_ADMIN_GUARD),
):
    return [
        RoleInfo(name=name, description=desc, assignable=True)
        for name, desc in _ASSIGNABLE_ROLES.items()
    ]


@router.get("/users", response_model=list[AdminUserSummary])
async def list_users(
    email: str | None = Query(default=None),
    q: str | None = Query(default=None),
    first: int = Query(default=0, ge=0),
    max: int = Query(default=50, ge=1, le=200),
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    users = await provider.list_users(
        email=email, search=q, first=first, max_results=max
    )
    return [AdminUserSummary(**u) for u in users]


@router.get("/users/{user_id}", response_model=AdminUserSummary)
async def get_user(
    user_id: str,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return AdminUserSummary(**await provider.get_user(user_id))


@router.post(
    "/users", response_model=AdminUserSummary, status_code=status.HTTP_201_CREATED
)
async def create_user(
    payload: CreateAdminUserRequest,
    context: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    roles = _resolve_create_roles(payload, actor=context)
    user = await provider.create_admin_user(
        email=payload.email,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        enabled=payload.enabled,
        send_verify_email=payload.send_verify_email,
        temporary_password=payload.temporary_password,
    )
    await provider.set_user_realm_roles(user["id"], roles)
    _record_role_audit(
        action="user.create",
        actor=context,
        target_user_id=user["id"],
        detail=f"roles={','.join(roles)}",
    )
    return AdminUserSummary(**await provider.get_user(user["id"]))


@router.patch("/users/{user_id}", response_model=AdminUserSummary)
async def update_user(
    user_id: str,
    payload: UpdateAdminUserRequest,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    user = await provider.update_user(
        user_id,
        enabled=payload.enabled,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    return AdminUserSummary(**user)


@router.post("/users/{user_id}/enabled", response_model=AdminUserSummary)
async def set_enabled(
    user_id: str,
    payload: SetEnabledRequest,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    return AdminUserSummary(**await provider.set_user_enabled(user_id, payload.enabled))


@router.post("/users/{user_id}/send-verify-email", status_code=status.HTTP_202_ACCEPTED)
async def send_verify_email(
    user_id: str,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    await provider.send_verify_email(user_id)
    return {"status": "accepted"}


@router.post("/users/{user_id}/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_user(
    user_id: str,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    await provider.logout_user_sessions(user_id)


@router.put("/users/{user_id}/roles", response_model=AdminUserSummary)
async def replace_roles(
    user_id: str,
    payload: SetRolesRequest,
    context: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    current = await provider.get_user_realm_roles(user_id)
    if (
        "super_admin" in current
        and "super_admin" not in payload.roles
        and not _is_super_admin(context)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super_admin may revoke super_admin",
        )
    if (
        context.subject == user_id
        and "admin" in current
        and "admin" not in payload.roles
    ):
        remaining_admins = await _count_admins(provider)
        if remaining_admins <= 1 and "super_admin" not in payload.roles:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own last admin role",
            )
    roles = _ensure_human_roles(_validate_role_names(payload.roles, actor=context))
    await provider.set_user_realm_roles(user_id, roles)
    _record_role_audit(
        action="roles.replace",
        actor=context,
        target_user_id=user_id,
        detail=f"roles={','.join(roles)}",
    )
    return AdminUserSummary(**await provider.get_user(user_id))


@router.post("/users/{user_id}/roles", response_model=AdminUserSummary)
async def add_roles(
    user_id: str,
    payload: AddRolesRequest,
    context: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    roles = _validate_role_names(payload.roles, actor=context)
    await provider.add_user_realm_roles(user_id, roles)
    _record_role_audit(
        action="roles.add",
        actor=context,
        target_user_id=user_id,
        detail=f"added={','.join(roles)}",
    )
    return AdminUserSummary(**await provider.get_user(user_id))


@router.delete("/users/{user_id}/roles/{role}", response_model=AdminUserSummary)
async def remove_role(
    user_id: str,
    role: str,
    context: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    _validate_role_names([role], actor=context)
    current = await provider.get_user_realm_roles(user_id)
    if role not in current:
        return AdminUserSummary(**await provider.get_user(user_id))
    remaining = _ensure_human_roles([r for r in current if r != role])
    if context.subject == user_id and role in {"admin", "super_admin"}:
        if role == "admin":
            remaining_admins = await _count_admins(provider)
            if remaining_admins <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove your own last admin role",
                )
    await provider.set_user_realm_roles(user_id, remaining)
    _record_role_audit(
        action="roles.remove",
        actor=context,
        target_user_id=user_id,
        detail=f"removed={role}",
    )
    return AdminUserSummary(**await provider.get_user(user_id))


@router.get("/groups", response_model=list[GroupInfo])
async def list_groups(
    search: str | None = Query(default=None),
    first: int = Query(default=0, ge=0),
    max: int = Query(default=100, ge=1, le=500),
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    groups = await provider.list_groups(search=search, first=first, max_results=max)
    return [GroupInfo(**g) for g in groups]


@router.post("/groups", response_model=GroupInfo, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: CreateGroupRequest,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    group = await provider.create_group(name=payload.name.strip())
    return GroupInfo(**group)


@router.post("/users/{user_id}/groups", status_code=status.HTTP_204_NO_CONTENT)
async def add_user_to_groups(
    user_id: str,
    payload: AddUserGroupsRequest,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    for group_id in payload.group_ids:
        await provider.add_user_to_group(user_id, group_id)


@router.get("/users/{user_id}/effective-access", response_model=EffectiveAccessSummary)
async def effective_access(
    user_id: str,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    roles = await provider.get_user_realm_roles(user_id)
    human_roles = [r for r in roles if r in _HUMAN_ROLES]
    groups_raw = await provider.list_user_groups(user_id)
    groups = [GroupInfo(**g) for g in groups_raw]
    notes = None
    if set(roles) - set(human_roles):
        notes = "Includes system/default Keycloak roles not shown in assignable set."
    return EffectiveAccessSummary(
        user_id=user_id,
        roles=human_roles or _ensure_human_roles(roles),
        groups=groups,
        notes=notes,
    )


@router.get("/custom-roles", response_model=list[CustomRoleInfo])
async def list_custom_roles(
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    from_keycloak = await provider.list_custom_realm_roles()
    merged = {r["name"]: CustomRoleInfo(**r) for r in from_keycloak}
    merged.update(_custom_roles_memory)
    return list(merged.values())


@router.post(
    "/custom-roles",
    response_model=CustomRoleInfo,
    status_code=status.HTTP_201_CREATED,
)
async def create_custom_role(
    payload: CreateCustomRoleRequest,
    _: AuthContext = Depends(_ADMIN_GUARD),
    provider: IIdentityProvider = Depends(get_identity_provider),
):
    name = payload.name.strip()
    try:
        created = await provider.create_custom_realm_role(
            name=name, description=payload.description
        )
        return CustomRoleInfo(**created)
    except HTTPException:
        info = CustomRoleInfo(
            name=name,
            description=payload.description,
            custom=True,
            storage="in-memory (Keycloak create failed; assign via Keycloak UI)",
        )
        _custom_roles_memory[name] = info
        return info


@router.get("/audit", response_model=list[AuditEvent])
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthContext = Depends(_ADMIN_GUARD),
):
    return list_audit_events(limit=limit)


async def _count_admins(provider: IIdentityProvider) -> int:
    users = await provider.list_users(first=0, max_results=200)
    return sum(
        1
        for u in users
        if "admin" in u.get("roles", []) or "super_admin" in u.get("roles", [])
    )

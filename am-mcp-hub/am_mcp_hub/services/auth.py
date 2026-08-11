from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Collection

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import httpx

from am_mcp_hub.core.config import get_settings
from am_mcp_hub.core.database import get_db_session
from am_mcp_hub.models.db import Organization, User

ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_VIEWER = "viewer"
ENVS = ("dev", "preprod", "prod")


def env_writer_role(env: str) -> str:
    return f"env_writer:{env}"


@dataclass(frozen=True, slots=True)
class AuthContext:
    subject: str
    org_slug: str
    email: str | None = None
    token: str | None = None
    roles: tuple[str, ...] = ()


def parse_role_map(raw: str) -> dict[str, list[str]]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, list[str]] = {}
    for key, val in data.items():
        if isinstance(val, str):
            roles = [val]
        elif isinstance(val, list):
            roles = [str(x) for x in val]
        else:
            continue
        out[str(key).strip().lower()] = roles
    return out


def resolve_roles(
    *,
    subject: str,
    email: str | None,
    is_admin_token: bool = False,
    is_bypass: bool = False,
    role_map_raw: str = "",
) -> tuple[str, ...]:
    if is_admin_token or is_bypass:
        return (ROLE_PLATFORM_ADMIN,)
    role_map = parse_role_map(role_map_raw)
    found: list[str] = []
    if email:
        found = list(role_map.get(email.strip().lower()) or [])
    if not found:
        found = list(role_map.get(subject.strip().lower()) or [])
    if not found:
        return (ROLE_VIEWER,)
    # Always include viewer so GETs remain allowed for writers.
    if ROLE_VIEWER not in found and ROLE_PLATFORM_ADMIN not in found:
        found.append(ROLE_VIEWER)
    return tuple(dict.fromkeys(found))


def is_platform_admin(ctx: AuthContext) -> bool:
    return ROLE_PLATFORM_ADMIN in ctx.roles


def can_write_env(ctx: AuthContext, env: str) -> bool:
    if is_platform_admin(ctx):
        return True
    return env_writer_role(env) in ctx.roles


def can_write_catalog(ctx: AuthContext) -> bool:
    return is_platform_admin(ctx)


async def _ensure_user(session: AsyncSession, ctx: AuthContext) -> User:
    settings = get_settings()
    org = (
        await session.execute(select(Organization).where(Organization.slug == ctx.org_slug))
    ).scalar_one_or_none()
    if org is None:
        org = Organization(slug=ctx.org_slug, name=ctx.org_slug)
        session.add(org)
        await session.flush()
    user = (
        await session.execute(
            select(User).where(User.org_id == org.id, User.subject == ctx.subject)
        )
    ).scalar_one_or_none()
    if user is None:
        user = User(org_id=org.id, subject=ctx.subject, email=ctx.email)
        session.add(user)
        await session.flush()
    return user


async def resolve_auth(request: Request, session: AsyncSession) -> AuthContext:
    settings = get_settings()
    auth = request.headers.get("Authorization") or ""
    token = ""
    # Inspector often sends bare "Bearer" with no token; treat as unauthenticated.
    if auth.lower().startswith("bearer"):
        token = auth[6:].lstrip(" :").strip()

    if settings.hub_dev_bypass_auth and not token:
        roles = resolve_roles(
            subject="dev-user",
            email=None,
            is_bypass=True,
            role_map_raw=settings.hub_role_map,
        )
        ctx = AuthContext(
            subject="dev-user",
            org_slug=settings.default_org_slug,
            email=None,
            roles=roles,
        )
        await _ensure_user(session, ctx)
        await session.commit()
        return ctx

    if settings.hub_admin_token and token == settings.hub_admin_token:
        roles = resolve_roles(
            subject="admin",
            email=None,
            is_admin_token=True,
            role_map_raw=settings.hub_role_map,
        )
        ctx = AuthContext(
            subject="admin",
            org_slug=settings.default_org_slug,
            email=None,
            token=token,
            roles=roles,
        )
        await _ensure_user(session, ctx)
        await session.commit()
        return ctx

    if not token:
        raise HTTPException(status_code=401, detail="Bearer token required")

    # Prefer identity introspection when available; fall back to opaque subject.
    subject = "asrax-user"
    email = None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.identity_url.rstrip('/')}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                subject = str(data.get("sub") or data.get("id") or subject)
                email = data.get("email")
    except httpx.HTTPError:
        subject = f"token:{token[:12]}"

    email_s = email if isinstance(email, str) else None
    roles = resolve_roles(
        subject=subject,
        email=email_s,
        role_map_raw=settings.hub_role_map,
    )
    ctx = AuthContext(
        subject=subject,
        org_slug=settings.default_org_slug,
        email=email_s,
        token=token,
        roles=roles,
    )
    await _ensure_user(session, ctx)
    await session.commit()
    return ctx


async def require_auth(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> AuthContext:
    return await resolve_auth(request, session)


def require_roles(*needed: str):
    """FastAPI dependency factory: require any of the given roles (or platform_admin)."""

    needed_set = set(needed)

    async def _dep(ctx: AuthContext = Depends(require_auth)) -> AuthContext:
        if is_platform_admin(ctx):
            return ctx
        if needed_set & set(ctx.roles):
            return ctx
        raise HTTPException(
            status_code=403,
            detail=f"requires one of roles: {sorted(needed_set)}",
        )

    return _dep


async def require_platform_admin(ctx: AuthContext = Depends(require_auth)) -> AuthContext:
    if not is_platform_admin(ctx):
        raise HTTPException(status_code=403, detail="requires platform_admin")
    return ctx


def require_env_write(env: str):
    async def _dep(ctx: AuthContext = Depends(require_auth)) -> AuthContext:
        want = (env or "").strip().lower()
        if want not in ENVS:
            raise HTTPException(status_code=400, detail=f"invalid env: {env!r}")
        if not can_write_env(ctx, want):
            raise HTTPException(
                status_code=403,
                detail=f"requires platform_admin or {env_writer_role(want)}",
            )
        return ctx

    return _dep


def assert_can_write_catalog(ctx: AuthContext) -> None:
    if not can_write_catalog(ctx):
        raise HTTPException(status_code=403, detail="requires platform_admin")


def assert_can_write_env(ctx: AuthContext, env: str) -> None:
    want = (env or "").strip().lower()
    if want not in ENVS:
        raise HTTPException(status_code=400, detail=f"invalid env: {env!r}")
    if not can_write_env(ctx, want):
        raise HTTPException(
            status_code=403,
            detail=f"requires platform_admin or {env_writer_role(want)}",
        )


def assert_roles(ctx: AuthContext, roles: Collection[str]) -> None:
    if is_platform_admin(ctx):
        return
    if set(roles) & set(ctx.roles):
        return
    raise HTTPException(status_code=403, detail=f"requires one of roles: {sorted(roles)}")

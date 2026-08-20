from __future__ import annotations

import asyncio
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.api.ui_schemas import (
    HomeSummaryResponse,
    MarketplaceMcpSyncRequest,
    MarketplaceMcpSyncResponse,
    ToolsIndexResponse,
)
from am_mcp_hub.core.config import get_settings
from am_mcp_hub.core.database import get_db_session
from am_mcp_hub.services.auth import AuthContext, require_auth
from am_mcp_hub.services.catalog import list_integrations, set_org_integration
from am_mcp_hub.services.inspect_report import load_inspect_report
from am_mcp_hub.services.marketplace import (
    build_marketplace,
    clear_marketplace_cache,
    _google_inspector_url,
    _inspector_url,
)
from am_mcp_hub.services.home_summary import build_home_summary_local
from am_mcp_hub.services.mcp_controls import set_launcher_enabled, set_write_enabled
from am_mcp_hub.services import local_creds as creds
from am_mcp_hub.services.refresh_probe import (
    annotate_in_cursor,
    cursor_sync_via_host,
    ide_servers_via_host,
    refresh_marketplace_item,
)
from am_mcp_hub.services.tools_index import build_tools_index

router = APIRouter(prefix="/api/v1")


class IntegrationOut(BaseModel):
    slug: str
    display_name: str
    adapter_type: str
    description: str | None = None
    enabled: bool
    vault_path: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class IntegrationPatch(BaseModel):
    enabled: bool | None = None
    vault_path: str | None = None
    settings: dict[str, Any] | None = None


@router.get("/integrations", response_model=list[IntegrationOut], tags=["integrations"], summary="List integrations")
async def get_integrations(
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    rows = await list_integrations(session, ctx.org_slug)
    return [
        IntegrationOut(
            slug=r.slug,
            display_name=r.display_name,
            adapter_type=r.adapter_type,
            description=r.description,
            enabled=r.enabled,
            vault_path=r.vault_path,
            settings=r.settings,
        )
        for r in rows
    ]


@router.patch("/integrations/{slug}", response_model=IntegrationOut, tags=["integrations"], summary="Update integration")
async def patch_integration(
    slug: str,
    body: IntegrationPatch,
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    row = await set_org_integration(
        session,
        org_slug=ctx.org_slug,
        slug=slug,
        enabled=body.enabled,
        vault_path=body.vault_path,
        settings=body.settings,
    )
    await session.commit()
    return IntegrationOut(
        slug=row.slug,
        display_name=row.display_name,
        adapter_type=row.adapter_type,
        description=row.description,
        enabled=row.enabled,
        vault_path=row.vault_path,
        settings=row.settings,
    )


@router.get("/me", tags=["integrations"], summary="Current auth context")
async def me(ctx: AuthContext = Depends(require_auth)):
    return {
        "subject": ctx.subject,
        "org_slug": ctx.org_slug,
        "email": ctx.email,
        "roles": list(ctx.roles),
    }


@router.get("/ui-config", tags=["ui"], summary="Public UI bootstrap")
async def ui_config():
    """Public UI bootstrap (no secrets beyond the local Inspector proxy token)."""
    settings = get_settings()
    inspector_url = _inspector_url(settings)
    return {
        "inspector_url": inspector_url,
        "google_inspector_url": _google_inspector_url(settings),
        "google_ui_url": "/google/",
        "inspector_base_url": (settings.inspector_public_url or "http://127.0.0.1:6274/").rstrip("/")
        + "/",
        "inspector_proxy_token": settings.inspector_proxy_auth_token,
        "tools_ui_url": "/tools/",
        "marketplace_url": "/marketplace/",
        "history_url": "/history/",
        "skills_url": "/skills/",
        "rules_url": "/rules/",
        "hooks_url": "/hooks/",
        "agents_url": "/agents/",
        "google_mcp_url": settings.google_workspace_mcp_public_url
        or "http://127.0.0.1:8130/google/mcp",
        "hub_mcp_url": "http://127.0.0.1:8130/mcp",
        "hub_sse_url": "http://127.0.0.1:8130/sse",
        "admin_url": "/admin/",
        "local_creds_only": True,
        "creds_persist_note": "Stored on host bind-mount; not uploaded; survives app delete",
        "catalog_mounts": {
            "asrax": settings.laptop_asrax_dir,
            "am": settings.laptop_am_dir,
        },
        "chat_memory_note": (
            "Chat history UI reads ~/.asrax/chat-memory via LAPTOP_ASRAX_DIR mount. "
            "Refresh with: am chat ingest-all"
        ),
        "inspector_note": (
            f"Open Inspector via inspector_url (token prefilled). "
            f"If Configuration asks for Proxy Session Token, paste: {settings.inspector_proxy_auth_token}"
        ),
    }


@router.get(
    "/home-summary",
    tags=["ui"],
    summary="Home workspace summary (laptop-local)",
    response_model=HomeSummaryResponse,
)
async def home_summary(
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    """Aggregate counts for Home. User vault stays on laptop mounts; no upload."""
    _ = ctx
    settings = get_settings()
    rows = await list_integrations(session, ctx.org_slug)
    local = await asyncio.to_thread(build_home_summary_local, rows, settings)

    from am_mcp_hub.services.google_status import google_status

    g = await google_status(settings, upstream_timeout=1.5)
    oauth = g.get("oauth") if isinstance(g.get("oauth"), dict) else {}
    upstream = g.get("upstream") if isinstance(g.get("upstream"), dict) else {}

    return {
        "hub": {"ok": True},
        "google": {
            "oauth_configured": bool(oauth.get("configured")),
            "upstream_ok": upstream.get("ok"),
        },
        "asrax": local["asrax"],
        "marketplace": local["marketplace"],
        "chat": local["chat"],
        "links": local["links"],
        "privacy": "laptop-local",
    }


@router.get(
    "/work-summary",
    tags=["ui"],
    summary="Role activity: hub tool audit, chats, agent access per org role",
)
async def work_summary(
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    _ = ctx
    from am_mcp_hub.services.work_summary import build_work_summary

    settings = get_settings()
    rows = await list_integrations(session, ctx.org_slug)
    return await build_work_summary(session, settings, rows)


@router.get(
    "/tools-index",
    tags=["ui"],
    summary="Flat tools index for Tools playground (laptop-local)",
    response_model=ToolsIndexResponse,
)
async def tools_index(
    q: str | None = None,
    mcp: str | None = None,
    scope: str = Query("all", pattern="^(all|hub|host)$"),
    kind: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    """Browse probed host tools + hub-callable /mcp tools. Call only works for hub scope."""
    _ = ctx
    rows = await list_integrations(session, ctx.org_slug)
    return await asyncio.to_thread(
        build_tools_index,
        rows,
        get_settings(),
        q=q,
        mcp=mcp,
        scope=cast(Literal["all", "hub", "host"], scope),
        kind=kind,
        limit=limit,
        offset=offset,
    )


@router.get("/google/status", tags=["google"], summary="Google Workspace proxy status")
async def google_workspace_status():
    from am_mcp_hub.services.google_status import google_status

    return await google_status(get_settings())


class MarketplaceControlsPatch(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    kind: str = Field(default="stdio-launcher")
    enabled: bool | None = None
    write_enabled: bool | None = None
    cred_target: str | None = None


@router.patch("/marketplace/controls", tags=["marketplace"], summary="Toggle marketplace item controls")
async def patch_marketplace_controls(
    body: MarketplaceControlsPatch,
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    """Toggle MCP on/off and write vs read-only for one marketplace item."""
    out: dict[str, Any] = {"slug": body.slug, "kind": body.kind}
    if body.enabled is not None:
        if body.kind == "hub-integration":
            row = await set_org_integration(
                session,
                org_slug=ctx.org_slug,
                slug=body.slug,
                enabled=body.enabled,
            )
            await session.commit()
            out["enabled"] = bool(row.enabled)
        else:
            ctrl = set_launcher_enabled(body.slug, enabled=body.enabled)
            out["enabled"] = ctrl["enabled"]
            out["enabled_key"] = ctrl["enabled_key"]
    if body.write_enabled is not None:
        ctrl = set_write_enabled(
            body.slug,
            enabled=body.write_enabled,
            cred_target=body.cred_target,
        )
        out["write_enabled"] = ctrl["write_enabled"]
        out["write_key"] = ctrl["write_key"]
        out["config_mode"] = ctrl["config_mode"]
    creds.load_into_environ(override=True)
    return {"controls": out}


class MarketplaceRefreshBody(BaseModel):
    slug: str = Field(min_length=1, max_length=120)
    live: bool = True


@router.post("/marketplace/refresh", tags=["marketplace"], summary="Refresh one marketplace card")
async def marketplace_refresh(
    body: MarketplaceRefreshBody,
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    """Refresh one Marketplace/Catalog card from report, optionally live-probing via host helper."""
    _ = ctx
    rows = await list_integrations(session, ctx.org_slug)
    clear_marketplace_cache()
    return await asyncio.to_thread(
        refresh_marketplace_item,
        slug=body.slug,
        integrations=rows,
        settings=get_settings(),
        live=body.live,
    )


@router.post(
    "/marketplace/cursor-sync",
    tags=["marketplace"],
    summary="Sync enabled MCPs into local IDE configs",
    response_model=MarketplaceMcpSyncResponse,
)
@router.post(
    "/marketplace/mcp-sync",
    tags=["marketplace"],
    summary="Sync enabled MCPs into local IDE configs",
    response_model=MarketplaceMcpSyncResponse,
)
async def marketplace_mcp_sync(
    body: MarketplaceMcpSyncRequest,
    ctx: AuthContext = Depends(require_auth),
):
    """Proxy to host probe-server to write enabled launchers into local IDE/LLM configs on this computer."""
    _ = ctx
    _ = body.scope  # reserved: only local laptop sync for now
    ides = [x.strip() for x in body.ides if str(x).strip()]
    return cursor_sync_via_host(
        force=body.force,
        ides=ides or None,
        settings=get_settings(),
    )


@router.get("/marketplace", tags=["marketplace"], summary="Marketplace catalog")
async def marketplace(
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    rows = await list_integrations(session, ctx.org_slug)
    settings = get_settings()

    def _load() -> dict[str, Any]:
        market = build_marketplace(rows, settings)
        ide = ide_servers_via_host(settings, timeout=1.0)
        servers: list[str] | None = None
        if ide and ide.get("ok"):
            raw = ide.get("servers") or []
            servers = [str(x) for x in raw if str(x).strip()] if isinstance(raw, list) else []
        return annotate_in_cursor(market, servers, ide_payload=ide)

    return await asyncio.to_thread(_load)


@router.get("/inspect-report", tags=["marketplace"], summary="Host MCP inspect report (full results)")
async def inspect_report(ctx: AuthContext = Depends(require_auth)):
    _ = ctx
    report = await asyncio.to_thread(load_inspect_report, get_settings())
    if report is None:
        return {
            "present": False,
            "path": None,
            "ok": 0,
            "total": 0,
            "ms": 0,
            "results": [],
        }
    return {
        "present": True,
        "path": report.get("_path"),
        "ok": report.get("ok"),
        "total": report.get("total"),
        "ms": report.get("ms"),
        "results": report.get("results") or [],
    }


@router.get("/catalog")
async def catalog_snapshot(ctx: AuthContext = Depends(require_auth)):
    from am_mcp_hub.services.laptop_catalog import catalog_overview

    return await asyncio.to_thread(catalog_overview, get_settings())

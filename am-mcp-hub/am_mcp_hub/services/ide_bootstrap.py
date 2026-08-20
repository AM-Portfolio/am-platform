"""IDE bootstrap entitlements for asrax.am-code."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.adapters.registry import build_tools
from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services import agent_profiles as profiles
from am_mcp_hub.services.auth import AuthContext, is_platform_admin
from am_mcp_hub.services.catalog import enabled_only
from am_mcp_hub.services.catalog_write import CatalogWriteError
from am_mcp_hub.services.ide_prompt import enrich_catalog_entries

_MUTATE_RE = re.compile(
    r"(write|delete|create|update|deploy|remove|set_|put_|post_|patch|grant|revoke|run_pipeline)",
    re.I,
)


def tool_mutates(name: str) -> bool:
    return bool(_MUTATE_RE.search(name))


def _viewer_only(ctx: AuthContext) -> bool:
    return (
        not is_platform_admin(ctx)
        and "env_writer:dev" not in ctx.roles
        and "env_writer:preprod" not in ctx.roles
        and "env_writer:prod" not in ctx.roles
    )


def _filter_agents(
    raw_agents: list[dict[str, Any]], ctx: AuthContext, settings: HubSettings
) -> list[dict[str, str]]:
    labeled: list[dict[str, str]] = []
    for a in raw_agents:
        aid = str(a.get("name") or a.get("id") or "").strip()
        if not aid:
            continue
        labeled.append({"id": aid, "label": str(a.get("label") or aid)})
    if is_platform_admin(ctx):
        return labeled
    if _viewer_only(ctx):
        try:
            pack = profiles.get_profile(settings, "developer") or {}
        except CatalogWriteError:
            pack = {}
        allowed = {str(x) for x in (pack.get("agents_default") or [])}
        if allowed:
            return [x for x in labeled if x["id"] in allowed]
        return labeled
    return labeled


async def build_ide_bootstrap(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    settings: HubSettings | None = None,
    request_base: str = "http://127.0.0.1:8130",
) -> dict[str, Any]:
    settings = settings or get_settings()
    try:
        data = await asyncio.to_thread(profiles.build_agents_bootstrap, settings)
    except CatalogWriteError:
        data = {"agents": [], "skills": [], "rules": []}
    agents = _filter_agents(list(data.get("agents") or []), ctx, settings)

    enabled = await enabled_only(session, ctx.org_slug)
    tools_raw = await build_tools(enabled)
    tools: list[dict[str, Any]] = []
    for t in tools_raw:
        name = str(t.get("name") or "")
        if not name:
            continue
        mutates = tool_mutates(name)
        if _viewer_only(ctx) and mutates:
            continue
        schema = t.get("inputSchema")
        item: dict[str, Any] = {
            "name": name,
            "description": str(t.get("description") or "")[:200],
            "mutates": mutates,
        }
        if isinstance(schema, dict):
            item["inputSchema"] = schema
        tools.append(item)

    base = request_base.rstrip("/")
    catalog_pack = enrich_catalog_entries(settings, data)
    return {
        "user": {
            "subject": ctx.subject,
            "email": ctx.email,
            "roles": list(ctx.roles),
            "org": ctx.org_slug,
        },
        "models": {
            "default": "together-llama-turbo",
            "allowed": [
                "together-llama-turbo",
                "together_ai/meta-llama/Meta-Llama-3-8B-Instruct-Lite",
                "together-bonsai",
                "Qwen/Qwen3-VL-8B-Instruct",
                "deepseek-chat",
                "gemini-2.0-flash",
            ],
        },
        "mcp": {
            "hubUrl": f"{base}/mcp",
            "tools": tools,
        },
        "agents": agents,
        "catalog": catalog_pack,
        "features": {
            "applyEdits": True,
            "tasks": False,
        },
        "limits": {
            "rpm": 30,
            "dailyTokens": 500_000,
            "maxToolSteps": 8,
        },
        "endpoints": {
            "chat": "/api/v1/ide/chat",
            "toolsExecute": "/api/v1/ide/tools/execute",
            "identity": settings.identity_url.rstrip("/"),
        },
    }

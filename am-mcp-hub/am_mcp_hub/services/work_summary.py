"""Org-profile work done: tasks from chats + tool execution counts per role."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.models.db import AuditEvent
from am_mcp_hub.services import agent_profiles as profiles
from am_mcp_hub.services import chat_memory as chat_mem
from am_mcp_hub.services import laptop_catalog as catalog
from am_mcp_hub.services.catalog import EnabledIntegration

_ORG_ROLE_IDS = ("developer", "qa", "management", "hr")
_ALIAS_TO_PRIMARY = {
    "dev": "developer",
    "admin": "management",
    "developer": "developer",
    "qa": "qa",
    "management": "management",
    "hr": "hr",
}


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


async def _audit_rows(session: AsyncSession) -> dict[str, Any]:
    top_tools = (
        await session.execute(
            select(AuditEvent.tool_name, func.count().label("n"))
            .where(AuditEvent.tool_name.is_not(None))
            .group_by(AuditEvent.tool_name)
            .order_by(desc("n"))
            .limit(40)
        )
    ).all()
    top_integ = (
        await session.execute(
            select(AuditEvent.integration_slug, func.count().label("n"))
            .where(AuditEvent.integration_slug.is_not(None))
            .group_by(AuditEvent.integration_slug)
            .order_by(desc("n"))
            .limit(40)
        )
    ).all()
    recent = (
        await session.execute(select(AuditEvent).order_by(desc(AuditEvent.created_at)).limit(80))
    ).scalars().all()
    total = (await session.execute(select(func.count()).select_from(AuditEvent))).scalar_one()
    return {
        "total_calls": int(total or 0),
        "top_tools": [{"name": r[0] or "(unknown)", "count": int(r[1])} for r in top_tools],
        "top_integrations": [{"name": r[0] or "(unknown)", "count": int(r[1])} for r in top_integ],
        "recent": [
            {
                "tool_name": e.tool_name,
                "integration_slug": e.integration_slug,
                "ok": e.ok,
                "detail": (e.detail or "")[:160],
                "created_at": _iso(e.created_at),
            }
            for e in recent
        ],
        "tool_counts": {str(r[0]): int(r[1]) for r in top_tools if r[0]},
        "integration_counts": {str(r[0]): int(r[1]) for r in top_integ if r[0]},
    }


def _match_tools_for_profile(
    profile_tools: list[str],
    tool_counts: dict[str, int],
    integration_counts: dict[str, int],
    recent: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    allow = {t.lower() for t in profile_tools}
    executed: list[dict[str, Any]] = []
    total = 0
    seen: set[str] = set()
    for slug, n in integration_counts.items():
        if slug.lower() in allow:
            executed.append({"id": slug, "name": slug, "kind": "mcp", "count": n})
            total += n
            seen.add(slug.lower())
    for name, n in tool_counts.items():
        low = name.lower()
        if low in seen:
            continue
        if low in allow or any(t in low for t in allow):
            executed.append({"id": name, "name": name, "kind": "tool", "count": n})
            total += n
    executed.sort(key=lambda x: -x["count"])
    recent_hits = [
        r
        for r in recent
        if (r.get("integration_slug") or "").lower() in allow
        or any(t in (r.get("tool_name") or "").lower() for t in allow)
    ][:15]
    return executed, total, recent_hits


def _chat_tasks_for_profile(
    chats: list[dict[str, Any]],
    *,
    keywords: list[str],
    label: str,
) -> list[dict[str, Any]]:
    keys = [k.lower() for k in keywords if k] + ([label.lower()] if label else [])
    out: list[dict[str, Any]] = []
    for row in chats:
        hay = " ".join(
            [
                str(row.get("title") or ""),
                str(row.get("preview") or ""),
                str(row.get("source") or ""),
            ]
        ).lower()
        if keys and not any(k in hay for k in keys):
            continue
        out.append(
            {
                "id": row.get("id"),
                "title": row.get("title") or row.get("preview") or row.get("id"),
                "source": row.get("source"),
                "updated_at": row.get("updated_at") or row.get("created_at"),
                "query_hint": hay[:120],
            }
        )
        if len(out) >= 20:
            break
    return out


def _agent_profile_id(settings: HubSettings, name: str, row: dict[str, Any]) -> str:
    binding = profiles.get_binding(settings, name)
    if binding and binding.get("profile"):
        return str(binding["profile"])
    hint = str(row.get("profile_hint") or "").strip()
    if hint:
        return hint
    defaults = profiles._DEFAULT_AGENT_BINDINGS.get(name) or {}
    return str(defaults.get("profile") or "")


def _agents_by_primary(settings: HubSettings) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, list[dict[str, Any]]] = {pid: [] for pid in _ORG_ROLE_IDS}
    for a in catalog.list_agents(settings):
        name = str(a.get("name") or "").strip()
        if not name:
            continue
        pid = _agent_profile_id(settings, name, a)
        primary = _ALIAS_TO_PRIMARY.get(pid)
        if primary is None:
            continue
        binding = profiles.get_binding(settings, name) or {}
        skills_add = list(binding.get("skills_add") or [])
        tools_add = list(binding.get("tools_add") or [])
        buckets[primary].append(
            {
                "name": name,
                "rel": a.get("rel"),
                "skills_count": len(skills_add),
                "tools_count": len(tools_add),
                "skills": skills_add,
                "tools": tools_add,
            }
        )
    return buckets


def _primary_org_profiles(settings: HubSettings) -> list[dict[str, Any]]:
    profiles.ensure_seed_profiles(settings)
    out: list[dict[str, Any]] = []
    for pid in _ORG_ROLE_IDS:
        p = profiles.get_profile(settings, pid)
        if p is not None:
            out.append(p)
    return out


async def build_work_summary(
    session: AsyncSession,
    settings: HubSettings,
    integrations: list[EnabledIntegration],
) -> dict[str, Any]:
    del integrations  # reserved for later MCP inventory; keep signature stable
    audit = await _audit_rows(session)
    chats = chat_mem.list_conversations(settings, limit=80)
    agents_map = _agents_by_primary(settings)
    org_profiles: list[dict[str, Any]] = []
    for p in _primary_org_profiles(settings):
        executed, total_calls, recent_hits = _match_tools_for_profile(
            list(p.get("tools") or []),
            audit["tool_counts"],
            audit["integration_counts"],
            audit["recent"],
        )
        tasks = _chat_tasks_for_profile(
            chats,
            keywords=list(p.get("task_keywords") or []),
            label=str(p.get("label") or p["id"]),
        )
        agents = agents_map.get(p["id"], [])
        for a in agents:
            a["skills_count"] = len(p.get("skills") or []) + int(a.get("skills_count") or 0)
            a["tools_count"] = len(p.get("tools") or []) + int(a.get("tools_count") or 0)
        org_profiles.append(
            {
                "id": p["id"],
                "label": p.get("label") or p["id"],
                "description": p.get("description") or "",
                "skills": p.get("skills") or [],
                "tools": p.get("tools") or [],
                "tools_missing": p.get("tools_missing") or [],
                "task_keywords": p.get("task_keywords") or [],
                "agents": agents,
                "tool_executions": executed,
                "tool_call_total": total_calls,
                "recent_tool_calls": recent_hits,
                "tasks_from_queries": tasks,
                "task_count": len(tasks),
            }
        )

    org_profiles.sort(key=lambda r: (-r["tool_call_total"], -r["task_count"], r["label"]))

    most_work: list[dict[str, Any]] = []
    if org_profiles:
        top = org_profiles[0]
        most_work.append(
            {
                "kind": "org_profile",
                "label": f"Most tool work: {top['label']}",
                "count": top["tool_call_total"],
                "hint": f"{top['task_count']} query tasks · {len(top['agents'])} agents",
                "profile_id": top["id"],
            }
        )
    if audit["top_tools"]:
        t = audit["top_tools"][0]
        most_work.append(
            {
                "kind": "hub_tool",
                "label": f"Top tool: {t['name']}",
                "count": t["count"],
                "hint": "Across all hub /mcp calls",
            }
        )
    busiest_tasks = max(org_profiles, key=lambda r: r["task_count"], default=None)
    if busiest_tasks and busiest_tasks["task_count"]:
        most_work.append(
            {
                "kind": "queries",
                "label": f"Most query tasks: {busiest_tasks['label']}",
                "count": busiest_tasks["task_count"],
                "hint": "Chats matching this role’s keywords",
                "profile_id": busiest_tasks["id"],
            }
        )

    sources = chat_mem.distinct_sources(settings)
    return {
        "privacy": "laptop-local",
        "org_profiles": org_profiles,
        "most_work": most_work,
        "audit": {
            "total_calls": audit["total_calls"],
            "top_tools": audit["top_tools"][:15],
            "top_integrations": audit["top_integrations"][:15],
            "recent": audit["recent"][:20],
        },
        "chat": {
            "total": sum(int(s.get("count") or 0) for s in sources),
            "sources": sources,
        },
        "links": {
            "history": "/history/",
            "agents": "/agents/",
            "tools": "/tools/",
            "marketplace": "/marketplace/",
        },
    }

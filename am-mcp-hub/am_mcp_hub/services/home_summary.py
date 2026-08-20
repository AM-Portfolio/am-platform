"""Compose laptop-local Home dashboard summary (no vault upload)."""

from __future__ import annotations

from typing import Any

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services import chat_memory as chat_mem
from am_mcp_hub.services.catalog import EnabledIntegration
from am_mcp_hub.services.laptop_catalog import _homes, catalog_counts
from am_mcp_hub.services.marketplace import _inspector_url, build_marketplace
from am_mcp_hub.services.refresh_probe import annotate_in_cursor, ide_servers_via_host


def build_home_summary_local(
    integrations: list[EnabledIntegration],
    settings: HubSettings | None = None,
) -> dict[str, Any]:
    """Blocking laptop/DB-free FS work for Home (run via to_thread)."""
    settings = settings or get_settings()
    counts = catalog_counts(settings)
    homes = [str(h) for h in _homes(settings)]

    sources = chat_mem.distinct_sources(settings)
    chat_total = sum(int(s.get("count") or 0) for s in sources)
    recent = chat_mem.list_conversations(settings, limit=5)
    recent_out = [
        {
            "id": r.get("id"),
            "title": r.get("title"),
            "source": r.get("source"),
            "profile_id": r.get("profile_id"),
            "updated_at": r.get("updated_at"),
            "created_at": r.get("created_at"),
        }
        for r in recent
    ]

    market = build_marketplace(integrations, settings)
    ide = ide_servers_via_host(settings, timeout=1.0)
    servers: list[str] | None = None
    if ide and ide.get("ok"):
        raw = ide.get("servers") or []
        servers = [str(x) for x in raw if str(x).strip()] if isinstance(raw, list) else []
    annotated = annotate_in_cursor(market, servers, ide_payload=ide)

    items = list(annotated.get("items") or [])
    needs_config = sum(
        1 for i in items if i.get("needs_config") and not i.get("configured")
    )
    m_counts = dict(annotated.get("counts") or {})
    inspect = dict(annotated.get("inspect_report") or {})
    inspect_slim = {
        "present": bool(inspect.get("present")),
        "path": inspect.get("path"),
        "ok": inspect.get("ok"),
        "total": inspect.get("total"),
        "ms": inspect.get("ms"),
    }
    targets = annotated.get("local_ide_targets")
    local_targets = [t for t in targets if isinstance(t, dict)] if isinstance(targets, list) else targets

    return {
        "asrax": {"counts": counts, "homes": homes},
        "marketplace": {
            "counts": {
                "total": m_counts.get("total"),
                "hub_integrations": m_counts.get("hub_integrations"),
                "stdio_launchers": m_counts.get("stdio_launchers"),
                "connected": m_counts.get("connected"),
                "disconnected": m_counts.get("disconnected"),
                "unknown": m_counts.get("unknown"),
                "configured": m_counts.get("configured"),
                "hub_tools": m_counts.get("hub_tools"),
                "probed_tools": m_counts.get("probed_tools"),
                "probe_ok": m_counts.get("probe_ok"),
                "needs_config": needs_config,
                "in_ide": m_counts.get("in_ide"),
            },
            "inspect_report": inspect_slim,
            "ide_helper": m_counts.get("ide_helper"),
            "ide_sync_hint": annotated.get("ide_sync_hint") or annotated.get("cursor_sync_hint"),
            "local_ide_targets": local_targets,
        },
        "chat": {
            "total": chat_total,
            "chat_memory_root": str(chat_mem.chat_memory_root(settings)),
            "sources": sources,
            "recent": recent_out,
        },
        "links": {
            "marketplace": "/marketplace/",
            "history": "/history/",
            "skills": "/skills/",
            "rules": "/rules/",
            "hooks": "/hooks/",
            "agents": "/agents/",
            "catalog": "/catalog/",
            "google": "/google/",
            "tools": "/tools/?scope=all",
            "tools_hub": "/tools/?scope=hub",
            "inspector_url": _inspector_url(settings),
        },
    }

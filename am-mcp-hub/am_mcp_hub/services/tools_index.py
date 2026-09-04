"""Flat tools index for admin Tools playground (laptop inspect + hub-callable names)."""

from __future__ import annotations

from typing import Any, Literal

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services.catalog import EnabledIntegration
from am_mcp_hub.services.inspect_report import load_inspect_report, tool_counts_by_name
from am_mcp_hub.services.marketplace import build_marketplace
from am_mcp_hub.services.tools_catalog import hub_core_tools, tools_for_adapter

Scope = Literal["all", "hub", "host"]


def hub_callable_tool_names(integrations: list[EnabledIntegration]) -> dict[str, str]:
    """Map hub /mcp tool name -> short description (static catalog, no live MCP)."""
    out: dict[str, str] = {}
    for t in hub_core_tools():
        name = str(t.get("name") or "").strip()
        if name:
            out[name] = str(t.get("description") or "")
    seen_adapters: set[str] = set()
    for integ in integrations:
        adapter = str(integ.adapter_type or "").strip()
        if not adapter or adapter in seen_adapters:
            continue
        seen_adapters.add(adapter)
        for t in tools_for_adapter(adapter):
            name = str(t.get("name") or "").strip()
            if name:
                out[name] = str(t.get("description") or "")
    return out


def _market_by_mcp(market: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for item in market.get("items") or []:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip()
        name = str(item.get("name") or "").strip()
        meta = {
            "slug": slug,
            "kind": str(item.get("kind") or ""),
            "configured": bool(item.get("configured")),
            "needs_config": bool(item.get("needs_config")),
            "display_name": name or slug,
        }
        for key in {slug, name, slug.replace("-", "_"), slug.replace("_", "-")}:
            if key:
                by.setdefault(key, meta)
    return by


def build_tools_index(
    integrations: list[EnabledIntegration],
    settings: HubSettings | None = None,
    *,
    q: str | None = None,
    mcp: str | None = None,
    scope: Scope = "all",
    kind: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    settings = settings or get_settings()
    limit = max(1, min(int(limit), 2000))
    offset = max(0, int(offset))
    scope_n = scope if scope in {"all", "hub", "host"} else "all"
    q_n = (q or "").strip().lower()
    mcp_n = (mcp or "").strip().lower()
    kind_n = (kind or "").strip().lower()

    hub_names = hub_callable_tool_names(integrations)
    market = build_marketplace(integrations, settings)
    by_mcp = _market_by_mcp(market)
    report = load_inspect_report(settings)
    probe = tool_counts_by_name(report)

    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_row(
        *,
        mcp_id: str,
        tool: str,
        ok: bool | None,
        description: str = "",
        force_callable: str | None = None,
    ) -> None:
        tool_n = tool.strip()
        mcp_id_n = mcp_id.strip() or "hub"
        if not tool_n:
            return
        key = (mcp_id_n.lower(), tool_n.lower())
        if key in seen:
            return
        seen.add(key)
        meta = by_mcp.get(mcp_id_n) or by_mcp.get(mcp_id_n.replace("-", "_")) or {}
        callable_kind = force_callable or ("hub" if tool_n in hub_names else "host")
        item_kind = str(meta.get("kind") or ("hub-integration" if callable_kind == "hub" and mcp_id_n == "hub" else "stdio-launcher"))
        rows.append(
            {
                "mcp": mcp_id_n,
                "tool": tool_n,
                "ok": ok,
                "kind": item_kind,
                "configured": bool(meta.get("configured", True)),
                "needs_config": bool(meta.get("needs_config", False)),
                "slug": str(meta.get("slug") or mcp_id_n),
                "callable": callable_kind,
                "description": description or hub_names.get(tool_n, ""),
            }
        )

    for mcp_name, prow in sorted(probe.items(), key=lambda x: x[0].lower()):
        names = list(prow.get("tool_names") or [])
        ok = bool(prow.get("ok")) if prow else None
        if names:
            for tname in names:
                add_row(mcp_id=mcp_name, tool=str(tname), ok=ok)
        else:
            # Probe count without names: still expose MCP as a category shell via placeholder skip
            pass

    for tname, desc in sorted(hub_names.items()):
        add_row(
            mcp_id="hub",
            tool=tname,
            ok=True,
            description=desc,
            force_callable="hub",
        )

    categories_map: dict[str, int] = {}
    for r in rows:
        categories_map[r["mcp"]] = categories_map.get(r["mcp"], 0) + 1

    filtered: list[dict[str, Any]] = []
    for r in rows:
        if scope_n == "hub" and r["callable"] != "hub":
            continue
        if scope_n == "host" and r["callable"] != "host":
            continue
        if mcp_n and r["mcp"].lower() != mcp_n:
            continue
        if kind_n and str(r.get("kind") or "").lower() != kind_n:
            continue
        if q_n:
            hay = f"{r['mcp']} {r['tool']} {r.get('description') or ''} {r.get('slug') or ''}".lower()
            if q_n not in hay:
                continue
        filtered.append(r)

    filtered.sort(key=lambda r: (0 if r["callable"] == "hub" else 1, r["mcp"].lower(), r["tool"].lower()))
    page = filtered[offset : offset + limit]

    hub_count = sum(1 for r in rows if r["callable"] == "hub")
    host_count = sum(1 for r in rows if r["callable"] == "host")
    categories = [
        {"mcp": k, "count": categories_map[k]}
        for k in sorted(categories_map, key=lambda x: x.lower())
    ]

    return {
        "items": page,
        "categories": categories,
        "counts": {
            "total": len(rows),
            "filtered": len(filtered),
            "hub": hub_count,
            "host": host_count,
            "mcps": len(categories_map),
            "returned": len(page),
        },
        "limit": limit,
        "offset": offset,
        "scope": scope_n,
        "inspect_present": report is not None,
        "privacy": "laptop-local",
    }

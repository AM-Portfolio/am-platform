"""Marketplace catalog: hub integrations + laptop MCP launchers + cred status."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services import local_creds as creds
from am_mcp_hub.services.catalog import EnabledIntegration
from am_mcp_hub.services.inspect_report import inspect_report_paths, load_inspect_report, tool_counts_by_name
from am_mcp_hub.services.laptop_catalog import list_mcp_launchers
from am_mcp_hub.services.mcp_controls import controls_for_slug
from am_mcp_hub.services.tools_catalog import hub_core_tools, marketplace_tools_for_integration

_MARKET_TTL_SEC = 15.0
_market_cache: dict[str, tuple[float, tuple[Any, ...], dict[str, Any]]] = {}


def _sample_configured(sample: str | None) -> bool:
    if not sample:
        return False
    target = creds.default_target(sample)
    try:
        text = creds.read_file(target)
    except ValueError:
        return False
    if not text.strip():
        return False
    keys = creds.parse_env_keys(text)
    return any(v.strip() for v in keys.values())


def _inspector_url(settings: HubSettings) -> str:
    from urllib.parse import urlencode

    base = (settings.inspector_public_url or "http://127.0.0.1:6274/").rstrip("/")
    qs = urlencode(
        {
            "transport": "sse",
            "serverUrl": settings.inspector_mcp_url
            if settings.inspector_mcp_url.endswith("/sse")
            else "http://hub:8130/sse",
            "MCP_PROXY_AUTH_TOKEN": settings.inspector_proxy_auth_token,
        }
    )
    return f"{base}/?{qs}"


def _google_inspector_url(settings: HubSettings) -> str:
    from urllib.parse import urlencode

    base = (settings.inspector_public_url or "http://127.0.0.1:6274/").rstrip("/")
    public = settings.google_workspace_mcp_public_url or "http://127.0.0.1:8130/google/mcp"
    # Inspector container must use docker DNS for hub proxy.
    server = "http://hub:8130/google/mcp" if "8130" in public else public
    qs = urlencode(
        {
            "transport": "streamable-http",
            "serverUrl": server,
            "MCP_PROXY_AUTH_TOKEN": settings.inspector_proxy_auth_token,
        }
    )
    return f"{base}/?{qs}"


def _market_fingerprint(
    integrations: list[EnabledIntegration],
    settings: HubSettings,
) -> tuple[Any, ...]:
    integ = tuple((i.slug, i.enabled, i.display_name, i.adapter_type) for i in integrations)
    mtimes: list[float] = []
    for path in inspect_report_paths(settings):
        try:
            mtimes.append(path.stat().st_mtime if path.is_file() else 0.0)
        except OSError:
            mtimes.append(0.0)
    bin_mtimes: list[float] = []
    for raw in (settings.laptop_asrax_dir, settings.laptop_am_dir):
        bin_dir = Path(raw).expanduser() / "bin"
        try:
            bin_mtimes.append(bin_dir.stat().st_mtime if bin_dir.is_dir() else 0.0)
        except OSError:
            bin_mtimes.append(0.0)
    return (integ, tuple(mtimes), tuple(bin_mtimes), settings.laptop_asrax_dir, settings.laptop_am_dir)


def clear_marketplace_cache() -> None:
    _market_cache.clear()


def build_marketplace(
    integrations: list[EnabledIntegration],
    settings: HubSettings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    fp = _market_fingerprint(integrations, settings)
    now = time.monotonic()
    hit = _market_cache.get("default")
    if hit is not None:
        expires_at, cached_fp, value = hit
        if expires_at > now and cached_fp == fp:
            return value

    built = _build_marketplace_uncached(integrations, settings)
    _market_cache["default"] = (now + _MARKET_TTL_SEC, fp, built)
    return built


def _build_marketplace_uncached(
    integrations: list[EnabledIntegration],
    settings: HubSettings,
) -> dict[str, Any]:
    creds.ensure_samples_copied()
    onboard = {str(item["slug"]): item for item in creds.onboard_catalog()}
    samples_by_id = {s["id"]: s for s in creds.list_samples()}
    launchers = list_mcp_launchers(settings)
    hub_inspector = _inspector_url(settings)
    google_inspector = _google_inspector_url(settings)
    report = load_inspect_report(settings)
    probe = tool_counts_by_name(report)

    items: list[dict[str, Any]] = []
    for integ in integrations:
        onboard_row = onboard.get(integ.slug) or {}
        sample = str(onboard_row.get("sample") or "") or None
        sample_meta = samples_by_id.get(sample or "") if sample else None
        needs_config = sample is not None
        configured = _sample_configured(sample) if needs_config else True
        inspector = google_inspector if integ.slug == "google-workspace" else hub_inspector
        hub_tools = marketplace_tools_for_integration(adapter_type=integ.adapter_type)
        probe_row = (
            probe.get(integ.slug)
            or probe.get(integ.slug.replace("-", "_"))
            or probe.get(integ.adapter_type)
            or probe.get(integ.adapter_type.replace("_", "-"))
        )
        # Prefer live host MCP tool count/names when probed (e.g. github=44).
        host_tool_count = int(probe_row["tools"]) if probe_row and probe_row.get("ok") else 0
        host_names = list(probe_row.get("tool_names") or []) if probe_row else []
        if host_names:
            tools = [{"name": n, "description": ""} for n in host_names]
        else:
            tools = hub_tools
        probe_ok = bool(probe_row and probe_row.get("ok")) if probe_row else None
        if probe_ok is True:
            connected = "connected"
        elif probe_ok is False:
            connected = "disconnected"
        else:
            connected = "unknown"
        ctrl = controls_for_slug(integ.slug, hub_enabled=integ.enabled)
        items.append(
            {
                "id": f"integration:{integ.slug}",
                "slug": integ.slug,
                "name": integ.display_name,
                "kind": "hub-integration",
                "description": integ.description or "",
                "enabled": ctrl["enabled"],
                "write_enabled": ctrl["write_enabled"],
                "write_key": ctrl["write_key"],
                "enabled_key": ctrl["enabled_key"],
                "config_mode": ctrl["config_mode"],
                "needs_config": needs_config,
                "configured": configured,
                "sample": sample,
                "cred_target": creds.default_target(sample) if sample else None,
                "sample_title": (sample_meta or {}).get("title"),
                "steps": list(onboard_row.get("steps") or []),
                "inspector_url": inspector,
                "tools": tools,
                "hub_tools": hub_tools,
                "tool_count": host_tool_count or len(tools),
                "hub_tool_count": len(hub_tools),
                "host_tool_count": host_tool_count,
                "probe_ok": probe_ok,
                "connected": connected,
                "probe_error": (
                    str(probe_row.get("error") or "")[:220] if probe_row and probe_ok is False else ""
                ),
                "tools_ui_url": f"/tools/?mcp={integ.slug}&scope=all",
                "configure_hint": (
                    "Fill client id/secret or API token in local credentials, then Reload."
                    if needs_config
                    else "No local secret file required for basic health tools."
                ),
            }
        )

    for launcher in launchers:
        name = str(launcher.get("name") or "")
        onboard_row = onboard.get(name) or {}
        sample = str(onboard_row.get("sample") or "") or None
        # Heuristic: map common launcher names to onboard samples
        if sample is None:
            for key, row in onboard.items():
                if key in name or name.startswith(key):
                    sample = str(row.get("sample") or "") or None
                    onboard_row = row
                    break
        needs_config = sample is not None
        configured = _sample_configured(sample) if needs_config else False
        probe_row = probe.get(name)
        host_tools = int(probe_row["tools"]) if probe_row else 0
        probe_ok = bool(probe_row.get("ok")) if probe_row else None
        host_names = list(probe_row.get("tool_names") or []) if probe_row else []
        tool_chips: list[dict[str, str]] = (
            [{"name": n, "description": ""} for n in host_names]
            if host_names
            else []
        )
        if probe_ok is True:
            connected = "connected"
        elif probe_ok is False:
            connected = "disconnected"
        else:
            connected = "unknown"
        cred_target = creds.default_target(sample) if sample else f"credentials.d/{name}.env"
        ctrl = controls_for_slug(name)
        items.append(
            {
                "id": f"launcher:{name}",
                "slug": name,
                "name": name,
                "kind": "stdio-launcher",
                "description": str(launcher.get("note") or "Host stdio MCP launcher"),
                "enabled": ctrl["enabled"],
                "write_enabled": ctrl["write_enabled"],
                "write_key": ctrl["write_key"],
                "enabled_key": ctrl["enabled_key"],
                "config_mode": ctrl["config_mode"],
                "configured": configured,
                "needs_config": True,
                "sample": sample,
                "cred_target": cred_target,
                "sample_title": None,
                "steps": list(onboard_row.get("steps") or [
                    "Create credentials.d entry if this MCP needs secrets",
                    "Run on host: am ai inspect <name> --connect",
                    "Refresh Marketplace after scripts/inspect_all_tools.py",
                ]),
                "launcher": launcher.get("launcher"),
                "path": launcher.get("path"),
                "inspector_url": hub_inspector,
                "tools": tool_chips,
                "hub_tools": [],
                "tool_count": host_tools,
                "hub_tool_count": 0,
                "host_tool_count": host_tools,
                "probe_ok": probe_ok,
                "connected": connected,
                "probe_error": (
                    str(probe_row.get("error") or "")[:220] if probe_row and probe_ok is False else ""
                ),
                "tools_ui_url": f"/tools/?mcp={name}&scope=all",
                "configure_hint": (
                    "Stdio launchers run on the host. "
                    "Tool counts come from the last am ai inspect --all report."
                ),
            }
        )

    items.sort(key=lambda x: (0 if x["kind"] == "hub-integration" else 1, str(x["name"]).lower()))
    core = hub_core_tools()
    return {
        "items": items,
        "counts": {
            "total": len(items),
            "hub_integrations": sum(1 for i in items if i["kind"] == "hub-integration"),
            "stdio_launchers": sum(1 for i in items if i["kind"] == "stdio-launcher"),
            "configured": sum(1 for i in items if i["configured"]),
            "hub_tools": sum(i.get("hub_tool_count") or 0 for i in items if i["kind"] == "hub-integration")
            + len(core),
            "probed_tools": sum(int(i.get("host_tool_count") or 0) for i in items),
            "probe_ok": sum(1 for i in items if i.get("probe_ok") is True),
            "connected": sum(1 for i in items if i.get("connected") == "connected"),
            "disconnected": sum(1 for i in items if i.get("connected") == "disconnected"),
            "unknown": sum(1 for i in items if i.get("connected") == "unknown"),
        },
        "hub_core_tools": core,
        "inspect_report": {
            "present": report is not None,
            "path": (report or {}).get("_path"),
            "ok": (report or {}).get("ok"),
            "total": (report or {}).get("total"),
            "ms": (report or {}).get("ms"),
        },
        "inspector_url": hub_inspector,
        "inspector_proxy_token": settings.inspector_proxy_auth_token,
        "tools_ui_url": "/tools/",
        "catalog_url": "/catalog/",
        "inspector_tools_hint": (
            "Full host MCP tool counts: open /catalog/ (from am ai inspect --all). "
            "Hub /tools/ only lists hub wrappers + google_workspace_*. "
            "Inspector List Tools after Connect shows the connected server only."
        ),
    }

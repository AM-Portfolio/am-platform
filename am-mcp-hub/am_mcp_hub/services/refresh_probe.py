"""Refresh one MCP card from inspect report, optionally live-probing via host helper."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services.catalog import EnabledIntegration
from am_mcp_hub.services.inspect_report import (
    load_inspect_report,
    merge_probe_result,
)
from am_mcp_hub.services.marketplace import build_marketplace


def _host_probe_url(settings: HubSettings) -> str:
    return (
        os.environ.get("AM_HOST_PROBE_URL")
        or getattr(settings, "host_probe_url", "")
        or ""
    ).strip()


def _host_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    settings: HubSettings | None = None,
    timeout: float = 60,
) -> dict[str, Any] | None:
    settings = settings or get_settings()
    base = _host_probe_url(settings).rstrip("/")
    if not base:
        return None
    url = f"{base}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def live_probe_via_host(name: str, settings: HubSettings | None = None) -> dict[str, Any] | None:
    """Ask the laptop probe helper (am ai probe-server) to re-connect one MCP."""
    data = _host_json(
        "/probe",
        method="POST",
        body={"name": name},
        settings=settings,
        timeout=200,
    )
    if not data:
        return None
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    if not isinstance(result, dict) or not result.get("name"):
        return None
    return result


def cursor_servers_via_host(
    settings: HubSettings | None = None,
    *,
    timeout: float = 1.0,
) -> list[str] | None:
    """Union of MCP server names across IDE configs (via host helper)."""
    data = ide_servers_via_host(settings, timeout=timeout)
    if not data or not data.get("ok"):
        return None
    raw = data.get("servers") or []
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if str(x).strip()]


def ide_servers_via_host(
    settings: HubSettings | None = None,
    *,
    timeout: float = 1.0,
) -> dict[str, Any] | None:
    data = _host_json("/ide-servers", method="GET", settings=settings, timeout=timeout)
    if data is None:
        data = _host_json("/cursor-servers", method="GET", settings=settings, timeout=timeout)
    return data


def _targets_from_ide_payload(data: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    if not data or not data.get("ok"):
        return None
    raw = data.get("targets")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    by_ide = data.get("by_ide") if isinstance(data.get("by_ide"), dict) else {}
    return [
        {
            "id": str(k),
            "label": str(k),
            "detected": True,
            "server_count": len(v) if isinstance(v, list) else 0,
            "local": True,
            "path": "",
        }
        for k, v in by_ide.items()
    ]


def cursor_sync_via_host(
    *,
    force: bool = False,
    ides: list[str] | None = None,
    settings: HubSettings | None = None,
) -> dict[str, Any]:
    """Ask host helper to sync enabled launchers into local IDE/LLM configs."""
    body: dict[str, Any] = {"force": force}
    if ides:
        body["ides"] = list(ides)
    data = _host_json(
        "/mcp-sync",
        method="POST",
        body=body,
        settings=settings,
        timeout=120,
    )
    if data is None:
        data = _host_json(
            "/cursor-sync",
            method="POST",
            body=body,
            settings=settings,
            timeout=120,
        )
    if not data:
        return {
            "ok": False,
            "error": (
                "Host probe-server unreachable. "
                "Start: am ai probe-server  (or run: am ai mcp-sync)"
            ),
        }
    return data


def local_ide_targets_via_host(settings: HubSettings | None = None) -> list[dict[str, Any]] | None:
    return _targets_from_ide_payload(ide_servers_via_host(settings))


def annotate_in_cursor(
    market: dict[str, Any],
    cursor_servers: list[str] | None,
    *,
    local_ide_targets: list[dict[str, Any]] | None = None,
    ide_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach in_ide / in_cursor flags. None means host helper unavailable.

    Pass ide_payload (or local_ide_targets) to avoid a second host round-trip.
    """
    known = set(cursor_servers or [])
    helper_up = cursor_servers is not None
    items = list(market.get("items") or [])
    in_ide_count = 0
    for item in items:
        if not helper_up:
            item["in_cursor"] = None
            item["in_ide"] = None
            continue
        slug = str(item.get("slug") or "")
        name = str(item.get("name") or "")
        if item.get("kind") == "hub-integration":
            present = (
                "asrax" in known
                or slug in known
                or name in known
            )
            if slug.replace("_", "-") in {"google-workspace", "google_workspace"} or slug in {
                "google_workspace",
                "google-workspace",
            }:
                present = "google-workspace" in known or present
        else:
            present = slug in known or name in known
        item["in_cursor"] = present  # back-compat
        item["in_ide"] = present
        if present:
            in_ide_count += 1
    counts = dict(market.get("counts") or {})
    counts["in_cursor"] = in_ide_count if helper_up else None
    counts["in_ide"] = in_ide_count if helper_up else None
    counts["cursor_helper"] = helper_up
    counts["ide_helper"] = helper_up
    market["counts"] = counts
    market["cursor_servers"] = list(known) if helper_up else None
    market["ide_servers"] = list(known) if helper_up else None
    market["cursor_sync_hint"] = (
        None
        if helper_up
        else "Start host helper (am ai probe-server) or run: am ai mcp-sync"
    )
    market["ide_sync_hint"] = market["cursor_sync_hint"]
    if local_ide_targets is not None:
        market["local_ide_targets"] = local_ide_targets
    elif ide_payload is not None:
        market["local_ide_targets"] = _targets_from_ide_payload(ide_payload) or []
    elif helper_up:
        market["local_ide_targets"] = local_ide_targets_via_host(get_settings()) or []
    else:
        market["local_ide_targets"] = None
    return market


def refresh_marketplace_item(
    *,
    slug: str,
    integrations: list[EnabledIntegration],
    settings: HubSettings | None = None,
    live: bool = True,
) -> dict[str, Any]:
    settings = settings or get_settings()
    mode = "report"
    probe_row: dict[str, Any] | None = None
    if live:
        probe_row = live_probe_via_host(slug, settings)
        if probe_row is not None:
            mode = "live"
            merge_probe_result(probe_row, settings)

    from am_mcp_hub.services.marketplace import clear_marketplace_cache

    clear_marketplace_cache()
    ide = ide_servers_via_host(settings, timeout=1.0)
    servers: list[str] | None = None
    if ide and ide.get("ok"):
        raw = ide.get("servers") or []
        servers = [str(x) for x in raw if str(x).strip()] if isinstance(raw, list) else []
    market = annotate_in_cursor(
        build_marketplace(integrations, settings),
        servers,
        ide_payload=ide,
    )
    items = list(market.get("items") or [])
    item = next(
        (
            i
            for i in items
            if str(i.get("slug") or "") == slug or str(i.get("name") or "") == slug
        ),
        None,
    )
    report = load_inspect_report(settings)
    report_row = None
    if report and isinstance(report.get("results"), list):
        for row in report["results"]:
            if isinstance(row, dict) and str(row.get("name") or "") == slug:
                report_row = row
                break

    hint = ""
    if mode == "report":
        hint = (
            "Reloaded from inspect report. "
            "For a live re-probe start host helper: "
            "python -m am_cli.probe_server  (AM_HOST_PROBE_URL=http://host.docker.internal:8765)"
        )
    return {
        "ok": True,
        "mode": mode,
        "slug": slug,
        "item": item,
        "report_row": report_row,
        "counts": market.get("counts"),
        "hint": hint,
    }

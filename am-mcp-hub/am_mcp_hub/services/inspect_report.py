"""Load last `am ai inspect --all` report from laptop mounts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from am_mcp_hub.core.config import HubSettings, get_settings


def inspect_report_paths(settings: HubSettings | None = None) -> list[Path]:
    settings = settings or get_settings()
    roots = [
        Path(settings.laptop_asrax_dir),
        Path(settings.laptop_am_dir),
        Path(settings.local_creds_dir),
    ]
    return [root / "mcp-inspect-all-report.json" for root in roots if str(root).strip()]


def _enrich_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item.setdefault("tool_names", [])
    if not item.get("ok") and not item.get("fail_hint"):
        item["fail_hint"] = _fail_hint(str(item.get("name") or ""), str(item.get("error") or ""))
    return item


def load_inspect_report(settings: HubSettings | None = None) -> dict[str, Any] | None:
    """Merge inspect reports from all mounts.

    A single-MCP refresh may write a tiny file under local-creds with a newer
    mtime than the full asrax report. Prefer per-name newest rows so one refresh
    cannot hide the rest of the catalog.
    """
    settings = settings or get_settings()
    by_name: dict[str, tuple[float, dict[str, Any]]] = {}
    sources: list[str] = []
    for path in inspect_report_paths(settings):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        rows = data.get("results")
        if not isinstance(rows, list):
            continue
        mtime = path.stat().st_mtime
        sources.append(str(path))
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            prev = by_name.get(name)
            if prev is None or mtime >= prev[0]:
                by_name[name] = (mtime, _enrich_row(row))
    if not by_name:
        return None
    results = [by_name[k][1] for k in sorted(by_name)]
    primary = max(
        ((Path(p).stat().st_mtime, p) for p in sources if Path(p).is_file()),
        default=(0.0, sources[0] if sources else ""),
        key=lambda t: t[0],
    )[1]
    return {
        "results": results,
        "total": len(results),
        "ok": sum(1 for r in results if r.get("ok")),
        "ms": 0,
        "_path": primary,
        "_paths": sources,
    }


def _fail_hint(name: str, error: str) -> str:
    err = error.lower()
    if "winerror 2" in err or "cannot find the file" in err:
        return "Missing binary on PATH (often npx/node). Install Node.js or fix PATH."
    if "youtube_client_id empty" in err:
        return "Missing YOUTUBE_CLIENT_ID in ~/.am/credentials.env."
    if "insufficient_scope" in err or "api token rejected" in err:
        return "Cloudflare token rejected / needs interactive OAuth."
    if "could not port-forward" in err or ("prometheus" in name and "port-forward" in err):
        return "Prometheus needs cluster access / port-forward (monitoring/prometheus). VPN/kubeconfig required."
    if "api_key_set=false" in err or (name == "grafana" and "expecting value" in err):
        return "Grafana auth incomplete — set GRAFANA_SERVICE_ACCOUNT_TOKEN."
    if "transport strategy: sse-only" in err or "mcp-remote" in err:
        return (
            "Remote MCP via mcp-remote hung (SSE/OAuth). Run the launcher once in a terminal, "
            "complete browser login, then retry."
        )
    if error:
        return error.split("|")[0].strip()[:220]
    return "Unknown failure"


def tool_counts_by_name(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not report:
        return out
    rows = report.get("results")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        names = row.get("tool_names")
        tool_names = (
            [str(n) for n in names if str(n).strip()]
            if isinstance(names, list)
            else []
        )
        out[name] = {
            "name": name,
            "ok": bool(row.get("ok")),
            "tools": int(row.get("tools") or 0),
            "server": str(row.get("server") or ""),
            "error": str(row.get("error") or ""),
            "ms": int(row.get("ms") or 0),
            "tool_names": tool_names,
            "fail_hint": str(row.get("fail_hint") or ""),
        }
    return out


def merge_probe_result(
    row: dict[str, Any],
    settings: HubSettings | None = None,
) -> list[str]:
    """Upsert one probe row into a writable inspect report. Returns paths written."""
    settings = settings or get_settings()
    name = str(row.get("name") or "").strip()
    if not name:
        return []

    payload = {
        "name": name,
        "ok": bool(row.get("ok")),
        "tools": int(row.get("tools") or 0),
        "ms": int(row.get("ms") or 0),
        "server": str(row.get("server") or ""),
        "error": str(row.get("error") or ""),
        "tool_names": [
            str(n) for n in (row.get("tool_names") or []) if str(n).strip()
        ]
        if isinstance(row.get("tool_names"), list)
        else [],
        "fail_hint": str(row.get("fail_hint") or ""),
    }
    if row.get("framing"):
        payload["framing"] = row.get("framing")

    # Seed from merged view so a local-creds write does not drop other MCPs.
    merged = load_inspect_report(settings) or {}
    seed_rows = list(merged.get("results") or []) if isinstance(merged.get("results"), list) else []

    written: list[str] = []
    candidates = [
        Path(settings.local_creds_dir) / "mcp-inspect-all-report.json",
        Path(settings.laptop_asrax_dir) / "mcp-inspect-all-report.json",
        Path(settings.laptop_am_dir) / "mcp-inspect-all-report.json",
    ]
    for path in candidates:
        if not str(path.parent).strip():
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_file():
                try:
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    data = loaded if isinstance(loaded, dict) else {}
                except (OSError, json.JSONDecodeError):
                    data = {}
            else:
                data = {}
            existing = list(data.get("results") or []) if isinstance(data.get("results"), list) else []
            # Prefer the richer of on-disk file vs merged seed.
            base = seed_rows if len(seed_rows) >= len(existing) else existing
            kept = [
                r
                for r in base
                if not (isinstance(r, dict) and str(r.get("name") or "") == name)
            ]
            kept.append(payload)
            kept.sort(key=lambda r: str((r or {}).get("name") or "") if isinstance(r, dict) else "")
            data["results"] = kept
            data["total"] = len(kept)
            data["ok"] = sum(1 for r in kept if isinstance(r, dict) and r.get("ok"))
            data["ms"] = int(data.get("ms") or 0)
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            written.append(str(path))
            break
        except OSError:
            continue
    return written

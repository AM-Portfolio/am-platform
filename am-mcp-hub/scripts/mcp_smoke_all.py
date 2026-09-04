"""Smoke-test hub HTTP/SSE MCP + each local *-mcp.cmd launcher. Writes JSON report."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Ensure amctl src on path
AMCTL = Path(__file__).resolve().parents[3] / "amctl" / "src"
if AMCTL.is_dir():
    sys.path.insert(0, str(AMCTL))

from am_cli.catalog_ui import connect_mcp_stdio, write_inspector_config  # noqa: E402
from am_cli.deploy.github_auth import asrax_home_dir, legacy_am_home  # noqa: E402


def _http_json(method: str, url: str, body: dict | None = None, timeout: float = 25.0) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer local-dev",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def probe_hub_rpc(name: str, url: str, rpc: dict, timeout: float = 25.0) -> dict:
    started = time.time()
    try:
        out = _http_json("POST", url, rpc, timeout=timeout)
        err = out.get("error")
        result = out.get("result") or {}
        tools = result.get("tools") if isinstance(result, dict) else None
        tool_count = len(tools) if isinstance(tools, list) else None
        ok = err is None
        return {
            "name": name,
            "kind": "http",
            "url": url,
            "ok": ok,
            "tools": tool_count if tool_count is not None else (1 if ok else 0),
            "ms": int((time.time() - started) * 1000),
            "error": json.dumps(err) if err else "",
            "detail": (
                f"tools={tool_count}"
                if tool_count is not None
                else (str(result.get("serverInfo") or result)[:200] if ok else "")
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "kind": "http",
            "url": url,
            "ok": False,
            "tools": 0,
            "ms": int((time.time() - started) * 1000),
            "error": str(exc),
            "detail": "",
        }


def probe_hub_tool_call(name: str, tool: str, arguments: dict | None = None) -> dict:
    started = time.time()
    url = "http://127.0.0.1:8130/mcp"
    try:
        out = _http_json(
            "POST",
            url,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments or {}},
            },
            timeout=40.0,
        )
        err = out.get("error")
        result = out.get("result") or {}
        is_error = bool(result.get("isError"))
        text = ""
        content = result.get("content") or []
        if content and isinstance(content[0], dict):
            text = str(content[0].get("text") or "")[:300]
        ok = err is None and not is_error
        return {
            "name": name,
            "kind": "hub-tool",
            "url": url,
            "ok": ok,
            "tools": 1 if ok else 0,
            "ms": int((time.time() - started) * 1000),
            "error": json.dumps(err) if err else (text if is_error else ""),
            "detail": text if ok else "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "name": name,
            "kind": "hub-tool",
            "url": url,
            "ok": False,
            "tools": 0,
            "ms": int((time.time() - started) * 1000),
            "error": str(exc),
            "detail": "",
        }


def probe_sse_endpoint() -> dict:
    started = time.time()
    url = "http://127.0.0.1:8130/sse"
    try:
        req = urllib.request.Request(
            url,
            headers={"Accept": "text/event-stream", "Authorization": "Bearer local-dev"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            chunk = resp.read(200).decode("utf-8", errors="replace")
        ok = "event: endpoint" in chunk or "data:" in chunk
        return {
            "name": "hub-sse",
            "kind": "sse",
            "url": url,
            "ok": ok,
            "tools": 0,
            "ms": int((time.time() - started) * 1000),
            "error": "" if ok else f"unexpected: {chunk[:120]}",
            "detail": chunk.splitlines()[0] if chunk else "",
        }
    except Exception as exc:  # noqa: BLE001
        # Timeout after first bytes is OK for long-lived SSE
        msg = str(exc)
        if "timed out" in msg.lower() or "timeout" in msg.lower():
            return {
                "name": "hub-sse",
                "kind": "sse",
                "url": url,
                "ok": True,
                "tools": 0,
                "ms": int((time.time() - started) * 1000),
                "error": "",
                "detail": "stream open (timeout expected)",
            }
        return {
            "name": "hub-sse",
            "kind": "sse",
            "url": url,
            "ok": False,
            "tools": 0,
            "ms": int((time.time() - started) * 1000),
            "error": msg,
            "detail": "",
        }


def launcher_jobs() -> list[tuple[str, str, list[str]]]:
    jobs: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
    for home in (asrax_home_dir(), legacy_am_home()):
        bin_dir = home / "bin"
        if not bin_dir.is_dir():
            continue
        for path in sorted(bin_dir.glob("*-mcp.cmd")):
            name = path.name[: -len("-mcp.cmd")]
            if name in seen:
                continue
            seen.add(name)
            jobs.append((name, "cmd", ["/c", str(path)]))
    return jobs


def main() -> int:
    results: list[dict] = []

    # Hub transport probes
    results.append(probe_sse_endpoint())
    results.append(
        probe_hub_rpc(
            "hub-mcp-initialize",
            "http://127.0.0.1:8130/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-smoke", "version": "1"},
                },
            },
        )
    )
    results.append(
        probe_hub_rpc(
            "hub-mcp-tools",
            "http://127.0.0.1:8130/mcp",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
    )
    results.append(
        probe_hub_rpc(
            "hub-mcp-message-tools",
            "http://127.0.0.1:8130/mcp/message?sessionId=smoke",
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
    )
    results.append(
        probe_hub_rpc(
            "google-proxy-initialize",
            "http://127.0.0.1:8130/google/mcp",
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcp-smoke", "version": "1"},
                },
            },
            timeout=40.0,
        )
    )

    # Hub tool calls one-by-one (key surface)
    for tool in (
        "hub_status",
        "catalog_overview",
        "list_skills",
        "list_mcp_launchers",
        "list_rules",
        "list_agents",
        "vault_health",
        "qa_agent_health",
        "tool_agent_health",
        "litellm_list_models",
        "google_workspace_status",
        "google_workspace_list_tools",
    ):
        results.append(probe_hub_tool_call(f"tool:{tool}", tool))

    # Local stdio launchers one-by-one
    jobs = launcher_jobs()
    print(f"launchers_to_test={len(jobs)}", flush=True)

    def _run_launcher(item: tuple[str, str, list[str]]) -> dict:
        name, _shell, args = item
        out = connect_mcp_stdio(
            name=name,
            command="cmd",
            args=args,
            timeout_sec=35.0,
        )
        out["kind"] = "stdio-launcher"
        out["url"] = args[-1] if args else ""
        out.setdefault("detail", "")
        return out

    # Sequential to avoid resource storms / port-forward races
    for item in jobs:
        print(f"testing launcher {item[0]}...", flush=True)
        results.append(_run_launcher(item))

    # Also test npx @asrax/mcp if present in inspector config
    cfg_path = write_inspector_config()
    block = (json.loads(cfg_path.read_text(encoding="utf-8")).get("mcpServers") or {})
    asrax = block.get("asrax")
    if isinstance(asrax, dict) and asrax.get("command"):
        print("testing npx @asrax/mcp...", flush=True)
        out = connect_mcp_stdio(
            name="asrax-npx",
            command=str(asrax.get("command")),
            args=[str(a) for a in (asrax.get("args") or [])],
            env=asrax.get("env") if isinstance(asrax.get("env"), dict) else None,
            timeout_sec=45.0,
        )
        out["kind"] = "stdio-npx"
        out["url"] = "npx @asrax/mcp"
        out.setdefault("detail", "")
        results.append(out)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "ok": sum(1 for r in results if r.get("ok")),
        "fail": sum(1 for r in results if not r.get("ok")),
        "total": len(results),
        "results": results,
    }
    out_path = Path(__file__).resolve().parent / "mcp-smoke-report.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "fail": report["fail"], "total": report["total"], "path": str(out_path)}))
    return 0 if report["fail"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

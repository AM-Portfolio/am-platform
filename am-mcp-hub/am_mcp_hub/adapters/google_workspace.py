"""Google Workspace via upstream workspace-mcp (Streamable HTTP)."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

import httpx

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services.catalog import EnabledIntegration

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def _tool(
    name: str,
    description: str,
    handler: ToolHandler,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties or {},
            "additionalProperties": True,
        },
        "handler": handler,
    }


def _mcp_url(settings: HubSettings, integ: EnabledIntegration) -> str:
    raw = ""
    if isinstance(integ.settings, dict):
        raw = str(integ.settings.get("mcp_url") or "").strip()
    return (raw or settings.google_workspace_mcp_url).rstrip("/")


def _public_url(settings: HubSettings, integ: EnabledIntegration) -> str:
    raw = ""
    if isinstance(integ.settings, dict):
        raw = str(integ.settings.get("public_mcp_url") or "").strip()
    return (raw or settings.google_workspace_mcp_public_url or _mcp_url(settings, integ)).rstrip(
        "/"
    )


async def _probe(url: str) -> dict[str, Any]:
    base = url[: -len("/mcp")] if url.endswith("/mcp") else url.rstrip("/")
    candidates = [f"{base}/health", url]
    last_err = ""
    async with httpx.AsyncClient(timeout=8.0) as client:
        for candidate in candidates:
            try:
                resp = await client.get(candidate)
                return {
                    "ok": resp.status_code < 500,
                    "status": resp.status_code,
                    "url": candidate,
                    "body": (resp.text or "")[:500],
                }
            except httpx.HTTPError as exc:
                last_err = str(exc)
    return {"ok": False, "error": last_err or "unreachable", "url": url}


async def _rpc(url: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        ctype = (resp.headers.get("content-type") or "").lower()
        if "application/json" in ctype:
            data = resp.json()
            if isinstance(data, dict):
                return data
            return {"ok": False, "status": resp.status_code, "body": data}
        return {
            "ok": resp.status_code < 300,
            "status": resp.status_code,
            "content_type": ctype,
            "body": (resp.text or "")[:2000],
        }


async def append_google_workspace_tools(
    tools: list[dict[str, Any]],
    *,
    settings: HubSettings,
    integ: EnabledIntegration,
) -> None:
    url = _mcp_url(settings, integ)
    public = _public_url(settings, integ)
    vault_path = integ.vault_path

    async def status(_: dict[str, Any]) -> dict[str, Any]:
        probe = await _probe(url)
        return {
            "ok": bool(probe.get("ok")),
            "integration": "google-workspace",
            "mcp_url": url,
            "inspector_url": public,
            "vault_path": vault_path,
            "ui": "Use official MCP Inspector (am ai inspect google-workspace)",
            "probe": probe,
        }

    tools.append(
        _tool(
            "google_workspace_status",
            "Probe workspace-mcp health and return Inspector connect URL",
            status,
        )
    )

    async def list_upstream(_: dict[str, Any]) -> dict[str, Any]:
        init = await _rpc(
            url,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "am-mcp-hub", "version": "0.1.0"},
            },
        )
        listed = await _rpc(url, "tools/list", {})
        result = listed.get("result") if isinstance(listed, dict) else None
        tool_rows: list[Any] = []
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            tool_rows = result["tools"]
        return {
            "ok": isinstance(result, dict),
            "inspector_url": public,
            "initialize": init,
            "tool_count": len(tool_rows),
            "tools": [
                {"name": t.get("name"), "description": t.get("description")}
                for t in tool_rows
                if isinstance(t, dict)
            ][:200],
        }

    tools.append(
        _tool(
            "google_workspace_list_tools",
            "List tools from upstream workspace-mcp (full UX is MCP Inspector)",
            list_upstream,
        )
    )

    async def call_upstream(args: dict[str, Any]) -> dict[str, Any]:
        name = str(args.get("name") or "").strip()
        if not name:
            return {"ok": False, "error": "name required"}
        arguments = args.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        await _rpc(
            url,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "am-mcp-hub", "version": "0.1.0"},
            },
        )
        out = await _rpc(url, "tools/call", {"name": name, "arguments": arguments})
        return {"ok": "error" not in out, "upstream": out, "inspector_url": public}

    tools.append(
        _tool(
            "google_workspace_call_tool",
            "Call one upstream workspace-mcp tool by name (prefer Inspector for exploration)",
            call_upstream,
            {
                "name": {"type": "string"},
                "arguments": {"type": "object"},
            },
        )
    )

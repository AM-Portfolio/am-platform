from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from am_mcp_hub.adapters.registry import build_tools
from am_mcp_hub.core.database import get_db_session
from am_mcp_hub.models.db import AuditEvent, Organization
from am_mcp_hub.services.auth import AuthContext, require_auth
from am_mcp_hub.services.catalog import enabled_only
from am_mcp_hub.services import sse_sessions

router = APIRouter(tags=["mcp"])


async def _tools_for(session: AsyncSession, ctx: AuthContext) -> list[dict[str, Any]]:
    enabled = await enabled_only(session, ctx.org_slug)
    return await build_tools(enabled)


async def _audit(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    tool_name: str,
    ok: bool,
    detail: str,
    integration_slug: str | None = None,
) -> None:
    org = (
        await session.execute(select(Organization).where(Organization.slug == ctx.org_slug))
    ).scalar_one_or_none()
    session.add(
        AuditEvent(
            org_id=org.id if org else None,
            user_subject=ctx.subject,
            integration_slug=integration_slug,
            tool_name=tool_name,
            ok=ok,
            detail=detail[:2000],
        )
    )
    await session.commit()


def _session_id(request: Request) -> str:
    existing = (request.headers.get("mcp-session-id") or "").strip()
    return existing or str(uuid.uuid4())


async def handle_mcp_message(
    message: dict[str, Any],
    session: AsyncSession,
    ctx: AuthContext,
) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")

    if method in {
        "notifications/initialized",
        "notifications/cancelled",
        "notifications/progress",
    }:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {"name": "am-mcp-hub", "version": "0.1.0"},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}

    if method == "tools/list":
        tools = await _tools_for(session, ctx)
        public = [
            {
                "name": t["name"],
                "description": t["description"],
                "inputSchema": t["inputSchema"],
            }
            for t in tools
        ]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": public}}

    if method == "resources/list":
        from am_mcp_hub.core.config import get_settings
        from am_mcp_hub.services.laptop_catalog import list_resources

        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"resources": list_resources(get_settings())},
        }

    if method == "resources/templates/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"resourceTemplates": []}}

    if method == "resources/read":
        from am_mcp_hub.core.config import get_settings
        from am_mcp_hub.services.laptop_catalog import read_resource

        params = message.get("params") or {}
        uri = str(params.get("uri") or "").strip()
        payload = read_resource(get_settings(), uri) if uri else None
        if payload is None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32002, "message": f"Resource not found: {uri}"},
            }
        return {"jsonrpc": "2.0", "id": msg_id, "result": payload}

    if method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "prompts": [
                    {
                        "name": "catalog_overview",
                        "description": "Summarize mounted laptop skills, agents, rules, and MCP launchers",
                        "arguments": [],
                    },
                    {
                        "name": "skill_detail",
                        "description": "Load one skill by name for the assistant",
                        "arguments": [
                            {
                                "name": "name",
                                "description": "Skill name (e.g. am-mcp)",
                                "required": True,
                            }
                        ],
                    },
                ]
            },
        }

    if method == "prompts/get":
        from am_mcp_hub.core.config import get_settings
        from am_mcp_hub.services.laptop_catalog import catalog_overview, get_skill

        params = message.get("params") or {}
        name = str(params.get("name") or "").strip()
        args = params.get("arguments") or {}
        settings = get_settings()
        if name == "catalog_overview":
            text = json.dumps(catalog_overview(settings), indent=2)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "description": "Laptop catalog overview",
                    "messages": [
                        {
                            "role": "user",
                            "content": {
                                "type": "text",
                                "text": f"Catalog overview:\n\n{text}",
                            },
                        }
                    ],
                },
            }
        if name == "skill_detail":
            skill_name = str(args.get("name") or "").strip()
            if not skill_name:
                got = None
            else:
                got = get_skill(settings, skill_name)
            body = got.get("raw") if got else json.dumps({"error": "skill not found or name required"}, indent=2)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "description": f"Skill {skill_name}",
                    "messages": [
                        {
                            "role": "user",
                            "content": {"type": "text", "text": body or ""},
                        }
                    ],
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": f"Unknown prompt: {name}"},
        }

    if method == "tools/call":
        params = message.get("params") or {}
        name = params.get("name")
        arguments = params.get("arguments") or {}
        tools = await _tools_for(session, ctx)
        match = next((t for t in tools if t["name"] == name), None)
        if match is None:
            await _audit(session, ctx, tool_name=str(name), ok=False, detail="unknown tool")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Unknown tool: {name}"},
            }
        try:
            result = await match["handler"](arguments if isinstance(arguments, dict) else {})
            await _audit(
                session,
                ctx,
                tool_name=str(name),
                ok=bool(result.get("ok", True)),
                detail=json.dumps(result, default=str)[:1500],
            )
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {"type": "text", "text": json.dumps(result, default=str, indent=2)}
                    ],
                    "isError": not bool(result.get("ok", True)),
                },
            }
        except Exception as exc:  # noqa: BLE001
            await _audit(session, ctx, tool_name=str(name), ok=False, detail=str(exc))
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            }

    if msg_id is None:
        return None
    # Sampling / completion / logging are client-driven; empty capability responses.
    if method in {"sampling/createMessage", "completion/complete"}:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": f"{method} not supported by am-mcp-hub (use tools/resources/prompts)",
            },
        }
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _json_mcp_response(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    session_id: str,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        payload,
        status_code=status_code,
        headers={
            "mcp-session-id": session_id,
            "cache-control": "no-cache",
        },
    )


@router.post(
    "/mcp",
    summary="Streamable HTTP MCP (JSON-RPC)",
    description=(
        "MCP Streamable HTTP transport. POST JSON-RPC (initialize, tools/list, tools/call). "
        "Prefer Accept: application/json (or both json + event-stream). "
        "Used by /tools UI and clients that speak Streamable HTTP."
    ),
)
@router.post(
    "/mcp/",
    summary="Streamable HTTP MCP (trailing slash alias)",
    description="Identical to POST /mcp. Alias for clients that append a trailing slash.",
)
async def mcp_post(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    accept = (request.headers.get("accept") or "").lower()
    session_id = _session_id(request)
    messages = body if isinstance(body, list) else [body]
    results: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        out = await handle_mcp_message(msg, session, ctx)
        if out is not None:
            results.append(out)

    # Prefer JSON when the client also accepts it. Inspector sends both Accept
    # types; finite SSE bodies crash its 0.16.x proxy.
    prefer_sse = "text/event-stream" in accept and "application/json" not in accept
    if prefer_sse:

        async def event_stream():
            for item in results:
                yield f"event: message\ndata: {json.dumps(item)}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "mcp-session-id": session_id,
                "cache-control": "no-cache",
            },
        )

    if not results:
        return Response(
            status_code=202,
            headers={"mcp-session-id": session_id, "cache-control": "no-cache"},
        )
    if len(results) == 1:
        return _json_mcp_response(results[0], session_id=session_id)
    return _json_mcp_response(results, session_id=session_id)


@router.get(
    "/mcp",
    summary="Streamable HTTP SSE channel / browser hint",
    description=(
        "Long-lived SSE keepalive for Streamable HTTP sessions. "
        "Browsers requesting text/html get a short hint page pointing at /tools."
    ),
)
@router.get(
    "/mcp/",
    summary="Streamable HTTP SSE (trailing slash alias)",
    description="Identical to GET /mcp. Alias for clients that append a trailing slash.",
)
async def mcp_get(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept and "text/event-stream" not in accept:
        return HTMLResponse(
            """<!doctype html>
<html lang="en"><head><meta charset="utf-8"/><title>AM MCP Hub</title>
<style>body{font-family:system-ui,sans-serif;max-width:40rem;margin:2rem auto;padding:0 1rem;line-height:1.45}
code{background:#f2f2f2;padding:0.1rem 0.35rem;border-radius:4px}</style></head>
<body>
<h1>This is the MCP endpoint, not a UI</h1>
<p>Open <a href="/marketplace/">Marketplace</a>, <a href="/tools/">Tools</a>, or <a href="/">hub home</a>.</p>
</body></html>"""
        )

    session_id = _session_id(request)

    async def event_stream():
        # Keep the stream open with heartbeats. Closing after one event crashes
        # @modelcontextprotocol/inspector@0.16.x proxy (all UI tabs fail).
        yield f": session {session_id}\n\n"
        try:
            while True:
                await asyncio.sleep(15)
                yield ": keepalive\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "mcp-session-id": session_id,
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
        },
    )


@router.delete(
    "/mcp",
    summary="End Streamable HTTP session",
    description="Deletes / ends an MCP Streamable HTTP session (mcp-session-id).",
)
@router.delete(
    "/mcp/",
    summary="End Streamable HTTP session (trailing slash alias)",
    description="Identical to DELETE /mcp. Alias for clients that append a trailing slash.",
)
async def mcp_delete(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    session_id = _session_id(request)
    return Response(
        status_code=200,
        headers={"mcp-session-id": session_id},
    )


@router.get(
    "/mcp/tools",
    summary="REST list of hub tools",
    description="Convenience JSON list of tools. Not the MCP wire protocol; use POST /mcp tools/list for MCP clients.",
)
async def list_tools_rest(
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    tools = await _tools_for(session, ctx)
    return {
        "tools": [
            {"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]}
            for t in tools
        ]
    }


def _public_base(request: Request) -> str:
    """URL Inspector's proxy (docker network) should call back to."""
    # Prefer docker service DNS for in-compose Inspector.
    forwarded = (request.headers.get("x-forwarded-host") or "").strip()
    if forwarded:
        proto = (request.headers.get("x-forwarded-proto") or "http").strip()
        return f"{proto}://{forwarded}".rstrip("/")
    host = (request.headers.get("host") or "").strip()
    if host.startswith("hub:") or host.startswith("127.0.0.1") or host.startswith("localhost"):
        return str(request.base_url).rstrip("/")
    # Calls from Inspector container use Host: hub:8130
    return "http://hub:8130"


@router.get(
    "/sse",
    summary="Classic MCP SSE (Inspector 0.16)",
    description=(
        "Open an SSE stream for MCP Inspector classic transport. "
        "First event is `endpoint` pointing at /mcp/message?sessionId=…. "
        "JSON-RPC replies are pushed as `event: message` on this same stream. "
        "Prefer this over Streamable HTTP for Inspector stability."
    ),
)
@router.get(
    "/sse/",
    summary="Classic MCP SSE (trailing slash alias)",
    description="Identical to GET /sse. Alias for clients that request a trailing slash (no redirect dependency).",
)
async def mcp_sse(
    request: Request,
    ctx: AuthContext = Depends(require_auth),
):
    session_id = str(uuid.uuid4())
    endpoint = f"{_public_base(request)}/mcp/message?sessionId={session_id}"
    queue = sse_sessions.open_session(session_id)

    async def event_stream():
        try:
            yield f"event: endpoint\ndata: {endpoint}\n\n"
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if item is None:
                    break
                yield f"event: message\ndata: {json.dumps(item)}\n\n"
        except asyncio.CancelledError:
            return
        finally:
            sse_sessions.close_session(session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "mcp-session-id": session_id,
            "x-accel-buffering": "no",
        },
    )


@router.post(
    "/mcp/message",
    summary="Classic SSE JSON-RPC messages",
    description=(
        "Follow-up JSON-RPC posts for a classic SSE session (sessionId from the endpoint event). "
        "When the SSE session is open, returns 202 and pushes replies on the SSE stream "
        "(MCP Inspector / SDK classic transport). Without an open session, returns JSON."
    ),
)
@router.post(
    "/mcp/message/",
    summary="Classic SSE messages (trailing slash alias)",
    description="Identical to POST /mcp/message. Alias for clients that append a trailing slash.",
)
async def mcp_sse_message(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    ctx: AuthContext = Depends(require_auth),
):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    messages = body if isinstance(body, list) else [body]
    results: list[dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        out = await handle_mcp_message(msg, session, ctx)
        if out is not None:
            results.append(out)

    sid = (request.query_params.get("sessionId") or _session_id(request)).strip()
    live = sse_sessions.get_session(sid) is not None
    if live:
        for item in results:
            await sse_sessions.publish(sid, item)
        return Response(status_code=202, headers={"mcp-session-id": sid})

    if not results:
        return Response(status_code=202, headers={"mcp-session-id": sid})
    if len(results) == 1:
        return _json_mcp_response(results[0], session_id=sid)
    return _json_mcp_response(results, session_id=sid)

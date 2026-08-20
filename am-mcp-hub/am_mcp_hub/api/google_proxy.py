"""Reverse-proxy Streamable HTTP to workspace-mcp with required Accept headers."""

from __future__ import annotations

import json
import re

import httpx
from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse

from am_mcp_hub.core.config import get_settings

router = APIRouter(tags=["google-proxy"])

_HOP = {
    "host",
    "content-length",
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
}

_SSE_DATA = re.compile(r"(?m)^data:\s*(.+)$")


def _upstream() -> str:
    return get_settings().google_workspace_mcp_url.rstrip("/")


def _forward_headers(request: Request) -> dict[str, str]:
    headers: dict[str, str] = {
        # Spec: clients must accept both; Inspector sometimes omits event-stream.
        "Accept": "application/json, text/event-stream",
        "Content-Type": request.headers.get("content-type") or "application/json",
    }
    for key in (
        "mcp-session-id",
        "mcp-protocol-version",
        "authorization",
        "last-event-id",
    ):
        val = request.headers.get(key)
        if val:
            headers[key] = val
    return headers


def _response_headers(upstream_resp: httpx.Response) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, val in upstream_resp.headers.items():
        if key.lower() in _HOP:
            continue
        out[key] = val
    return out


def _sse_to_json_body(raw: bytes) -> bytes | None:
    """Unwrap a short SSE body to JSON so Inspector's proxy does not crash on stream end."""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    payloads: list[str] = []
    for match in _SSE_DATA.finditer(text):
        chunk = match.group(1).strip()
        if chunk and chunk != "{}":
            payloads.append(chunk)
    if not payloads:
        return None
    last = payloads[-1]
    try:
        json.loads(last)
    except json.JSONDecodeError:
        return None
    return last.encode("utf-8")


@router.api_route(
    "/google/mcp",
    methods=["GET", "POST", "DELETE"],
    summary="Google Workspace MCP proxy",
    description=(
        "Reverse-proxy to workspace-mcp with required Accept headers. "
        "Point MCP Inspector (streamable-http) or Cursor at this URL instead of :8000 directly."
    ),
)
@router.api_route(
    "/google/mcp/",
    methods=["GET", "POST", "DELETE"],
    summary="Google Workspace MCP proxy (trailing slash alias)",
    description="Identical to /google/mcp. Alias for clients that append a trailing slash.",
)
async def google_mcp_proxy(request: Request):
    accept = (request.headers.get("accept") or "").lower()
    if request.method == "GET" and "text/html" in accept and "text/event-stream" not in accept:
        return HTMLResponse(
            """<!doctype html><html><head><meta charset="utf-8"/>
<meta http-equiv="refresh" content="0;url=/google/"/>
<title>Google Workspace MCP</title></head><body>
<p>Google Workspace UI is at <a href="/google/">/google/</a>.</p>
<p><code>:8000/</code> is health JSON only. MCP endpoint:
<code>http://127.0.0.1:8130/google/mcp</code></p>
</body></html>"""
        )

    upstream = _upstream()
    body = await request.body()
    headers = _forward_headers(request)

    try:
        client = httpx.AsyncClient(timeout=120.0)
        req = client.build_request(
            request.method,
            upstream,
            headers=headers,
            content=body if body else None,
        )
        upstream_resp = await client.send(req, stream=True)
    except httpx.HTTPError as exc:
        return Response(
            content=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32000,
                        "message": f"google-workspace upstream unreachable: {exc}",
                    },
                }
            ),
            media_type="application/json",
            status_code=502,
        )

    resp_headers = _response_headers(upstream_resp)
    ctype = (upstream_resp.headers.get("content-type") or "").lower()
    is_sse = "text/event-stream" in ctype

    # Buffer POST/DELETE SSE into JSON. Streaming a finite SSE body crashes
    # MCP Inspector 0.16.x proxy ("Controller is already closed" -> session token errors).
    if request.method != "GET" and is_sse:
        data = b""
        try:
            async for chunk in upstream_resp.aiter_bytes():
                data += chunk
        finally:
            await upstream_resp.aclose()
            await client.aclose()
        json_body = _sse_to_json_body(data)
        if json_body is not None:
            clean = {
                k: v
                for k, v in resp_headers.items()
                if k.lower() not in {"content-type", "content-length"}
            }
            return Response(
                content=json_body,
                status_code=upstream_resp.status_code,
                headers=clean,
                media_type="application/json",
            )
        return Response(
            content=data,
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=upstream_resp.headers.get("content-type") or "text/event-stream",
        )

    async def stream():
        try:
            async for chunk in upstream_resp.aiter_bytes():
                yield chunk
        finally:
            await upstream_resp.aclose()
            await client.aclose()

    if is_sse or request.method == "GET":
        return StreamingResponse(
            stream(),
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=upstream_resp.headers.get("content-type") or "text/event-stream",
        )

    data = b""
    try:
        async for chunk in upstream_resp.aiter_bytes():
            data += chunk
    finally:
        await upstream_resp.aclose()
        await client.aclose()

    return Response(
        content=data,
        status_code=upstream_resp.status_code,
        headers=resp_headers,
        media_type=upstream_resp.headers.get("content-type") or "application/json",
    )

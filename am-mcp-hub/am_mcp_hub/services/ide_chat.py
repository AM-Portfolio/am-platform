"""IDE chat proxy to LiteLLM + simple per-subject RPM limit."""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services.auth import AuthContext

_rpm_window: dict[str, tuple[float, int]] = {}
_daily_tokens: dict[str, tuple[str, int]] = {}


class IdeQuotaExceeded(Exception):
    def __init__(self, detail: str, limits: dict[str, int]) -> None:
        super().__init__(detail)
        self.detail = detail
        self.limits = limits


def _day_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def check_and_bump_rpm(subject: str, *, rpm: int) -> None:
    now = time.time()
    start, count = _rpm_window.get(subject, (now, 0))
    if now - start >= 60:
        start, count = now, 0
    if count >= rpm:
        raise IdeQuotaExceeded("rpm limit exceeded", {"rpm": rpm})
    _rpm_window[subject] = (start, count + 1)


def check_daily_tokens(subject: str, *, daily_tokens: int, add: int = 0) -> None:
    day = _day_key()
    cur_day, used = _daily_tokens.get(subject, (day, 0))
    if cur_day != day:
        cur_day, used = day, 0
    if used + add > daily_tokens:
        raise IdeQuotaExceeded("daily token limit exceeded", {"dailyTokens": daily_tokens})
    _daily_tokens[subject] = (cur_day, used + add)


def _master_key(settings: HubSettings | None = None) -> str:
    env = (os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("AM_LITELLM_API_KEY") or "").strip()
    if env:
        return env
    settings = settings or get_settings()
    return (settings.litellm_master_key or "").strip()


async def stream_ide_chat(
    ctx: AuthContext,
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    settings: HubSettings | None = None,
    rpm: int = 30,
    daily_tokens: int = 500_000,
) -> AsyncIterator[str]:
    settings = settings or get_settings()
    check_and_bump_rpm(ctx.subject, rpm=rpm)
    check_daily_tokens(ctx.subject, daily_tokens=daily_tokens, add=0)

    trace_id = str(uuid.uuid4())
    yield f"event: meta\ndata: {json.dumps({'trace_id': trace_id})}\n\n"

    base = settings.litellm_url.rstrip("/")
    key = _master_key(settings)
    if not key:
        yield f"event: error\ndata: {json.dumps({'detail': 'LiteLLM master key not configured on Hub (set LITELLM_MASTER_KEY)', 'trace_id': trace_id})}\n\n"
        return
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    headers["Authorization"] = f"Bearer {key}"

    body: dict[str, Any] = {
        "model": model or "together-llama-turbo",
        "messages": messages,
        "stream": True,
        "temperature": 0.2,
    }
    if tools:
        body["tools"] = tools
        if tool_choice is not None:
            body["tool_choice"] = tool_choice
        else:
            body["tool_choice"] = "auto"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{base}/v1/chat/completions",
                headers=headers,
                json=body,
            ) as resp:
                if resp.status_code >= 400:
                    text = (await resp.aread()).decode("utf-8", errors="replace")[:800]
                    yield f"event: error\ndata: {json.dumps({'detail': text, 'status': resp.status_code, 'trace_id': trace_id})}\n\n"
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            yield f"event: done\ndata: {json.dumps({'trace_id': trace_id})}\n\n"
                            return
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        usage = chunk.get("usage") or {}
                        total = int(usage.get("total_tokens") or 0)
                        if total:
                            check_daily_tokens(ctx.subject, daily_tokens=daily_tokens, add=total)
                        yield f"event: chunk\ndata: {json.dumps({'chunk': chunk, 'trace_id': trace_id})}\n\n"
                yield f"event: done\ndata: {json.dumps({'trace_id': trace_id})}\n\n"
    except IdeQuotaExceeded as exc:
        yield f"event: error\ndata: {json.dumps({'detail': exc.detail, 'code': 'quota', 'limits': exc.limits, 'trace_id': trace_id})}\n\n"
    except httpx.HTTPError as exc:
        yield f"event: error\ndata: {json.dumps({'detail': str(exc), 'trace_id': trace_id})}\n\n"

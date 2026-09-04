"""LLM provider chat helpers for task analyze / report assist."""

from __future__ import annotations

from typing import Any

import httpx

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services.task_connections import resolve_auth


async def chat(settings: HubSettings, conn: dict[str, Any], *, system: str, user: str) -> str:
    kind = conn.get("kind")
    key = resolve_auth(conn)
    if kind == "openai_compatible":
        return await _openai_chat(settings, conn, key=key, system=system, user=user)
    if kind == "gemini":
        return await _gemini_chat(conn, key=key, system=system, user=user)
    if kind == "anthropic":
        return await _anthropic_chat(conn, key=key, system=system, user=user)
    raise RuntimeError(f"chat not supported for kind={kind}")


async def _openai_chat(
    settings: HubSettings,
    conn: dict[str, Any],
    *,
    key: str,
    system: str,
    user: str,
) -> str:
    base = (conn.get("base_url") or settings.litellm_url).rstrip("/")
    model = conn.get("model") or "gpt-4o-mini"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{base}/v1/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return str((((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or "")


async def _gemini_chat(conn: dict[str, Any], *, key: str, system: str, user: str) -> str:
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing")
    model = conn.get("model") or "gemini-2.5-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={key}"
    )
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            url,
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
        return "".join(str(p.get("text") or "") for p in parts)


async def _anthropic_chat(conn: dict[str, Any], *, key: str, system: str, user: str) -> str:
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    model = conn.get("model") or "claude-sonnet-4-5"
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        blocks = data.get("content") or []
        return "".join(str(b.get("text") or "") for b in blocks if b.get("type") == "text")

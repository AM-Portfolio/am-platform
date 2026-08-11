"""In-memory classic MCP SSE sessions: POST replies ride the open GET /sse stream."""

from __future__ import annotations

import asyncio
from typing import Any

_SESSIONS: dict[str, asyncio.Queue[dict[str, Any] | None]] = {}


def open_session(session_id: str) -> asyncio.Queue[dict[str, Any] | None]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    _SESSIONS[session_id] = queue
    return queue


def close_session(session_id: str) -> None:
    queue = _SESSIONS.pop(session_id, None)
    if queue is None:
        return
    try:
        queue.put_nowait(None)
    except asyncio.QueueFull:
        pass


def get_session(session_id: str) -> asyncio.Queue[dict[str, Any] | None] | None:
    return _SESSIONS.get(session_id)


async def publish(session_id: str, message: dict[str, Any]) -> bool:
    queue = _SESSIONS.get(session_id)
    if queue is None:
        return False
    await queue.put(message)
    return True

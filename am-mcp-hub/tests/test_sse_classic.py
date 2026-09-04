from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from am_mcp_hub.core import database as dbmod
from am_mcp_hub.core.config import get_settings
from am_mcp_hub.main import app
from am_mcp_hub.services import sse_sessions


@pytest.fixture(autouse=True)
def _sqlite_settings(tmp_path, monkeypatch):
    db_path = tmp_path / "hub.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("HUB_DEV_BYPASS_AUTH", "1")
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None
    yield
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None
    # Avoid leaked sessions across tests
    for sid in list(getattr(sse_sessions, "_SESSIONS", {})):
        sse_sessions.close_session(sid)


@pytest.mark.asyncio
async def test_sse_sessions_publish_roundtrip():
    q = sse_sessions.open_session("s1")
    assert sse_sessions.get_session("s1") is q
    ok = await sse_sessions.publish("s1", {"jsonrpc": "2.0", "id": 1, "result": {}})
    assert ok is True
    assert (await q.get())["id"] == 1
    sse_sessions.close_session("s1")
    assert sse_sessions.get_session("s1") is None


@pytest.mark.asyncio
async def test_classic_sse_message_pushes_to_open_session():
    """Inspector SDK cancels POST bodies; replies must be queued for the SSE stream."""
    from am_mcp_hub.core.database import init_db

    await init_db()
    sid = "inspector-sess-1"
    queue = sse_sessions.open_session(sid)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        post = await client.post(
            f"/mcp/message?sessionId={sid}",
            headers={
                "Authorization": "Bearer",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert post.status_code == 202
        item = await asyncio.wait_for(queue.get(), timeout=2.0)
        assert item["id"] == 1
        assert item["result"]["serverInfo"]["name"] == "am-mcp-hub"

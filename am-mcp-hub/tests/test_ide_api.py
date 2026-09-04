"""IDE bootstrap / plan-mode tool filter / chat headers."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from am_mcp_hub.api.ide_router import _tools_for_mode
from am_mcp_hub.core.config import get_settings
from am_mcp_hub.core import database as dbmod
from am_mcp_hub.main import app


@pytest.fixture(autouse=True)
def _sqlite_settings(tmp_path, monkeypatch):
    db_path = tmp_path / "hub_ide.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("HUB_DEV_BYPASS_AUTH", "1")
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None
    yield
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None


def test_normalize_tool_calls_adds_type():
    from am_mcp_hub.api.ide_router import _normalize_tool_calls

    raw = [{"id": "c1", "function": {"name": "hub_status", "arguments": "{}"}}]
    out = _normalize_tool_calls(raw)
    assert out == [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "hub_status", "arguments": "{}"},
        }
    ]


def test_plan_mode_filters_mutating_tools():
    tools = [
        {"type": "function", "function": {"name": "ide_read_file"}},
        {"type": "function", "function": {"name": "ide_write_file"}},
        {"type": "function", "function": {"name": "hub_status"}},
        {"type": "function", "function": {"name": "ide_run_terminal"}},
    ]
    filtered = _tools_for_mode("plan", tools)
    names = [((t.get("function") or {}).get("name")) for t in (filtered or [])]
    assert "ide_read_file" in names
    assert "hub_status" in names
    assert "ide_write_file" not in names
    assert "ide_run_terminal" not in names


def test_ask_mode_strips_tools():
    tools = [{"type": "function", "function": {"name": "hub_status"}}]
    assert _tools_for_mode("ask", tools) is None


@pytest.mark.asyncio
async def test_ide_bootstrap_and_chat_sse_headers():
    from am_mcp_hub.core.database import init_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await init_db()
        boot = await client.get("/api/v1/ide/bootstrap")
        assert boot.status_code == 200
        body = boot.json()
        assert body["endpoints"]["chat"] == "/api/v1/ide/chat"
        assert "models" in body

        # Without LiteLLM key, stream should still be SSE with meta/error events
        chat = await client.post(
            "/api/v1/ide/chat",
            json={"messages": [{"role": "user", "content": "hi"}], "mode": "ask"},
        )
        assert chat.status_code == 200
        assert "text/event-stream" in (chat.headers.get("content-type") or "")
        assert chat.headers.get("x-accel-buffering") == "no"
        assert "no-cache" in (chat.headers.get("cache-control") or "")
        text = chat.text
        assert "event: meta" in text

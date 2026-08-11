from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from am_mcp_hub.core.config import get_settings
from am_mcp_hub.core import database as dbmod
from am_mcp_hub.main import app


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


@pytest.mark.asyncio
async def test_health_and_integrations_and_mcp_tools():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # lifespan not auto-run with ASGITransport unless we trigger — call init_db
        from am_mcp_hub.core.database import init_db

        await init_db()

        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["service"] == "am-mcp-hub"

        tools_page = await client.get("/tools/")
        assert tools_page.status_code == 200
        assert b"Connected tools" in tools_page.content

        market_page = await client.get("/marketplace/")
        assert market_page.status_code == 200
        assert b"AM MCP Marketplace" in market_page.content

        google_page = await client.get("/google/")
        assert google_page.status_code == 200
        assert b"Google Workspace MCP" in google_page.content

        ui = await client.get("/api/v1/ui-config")
        assert ui.status_code == 200
        ui_body = ui.json()
        assert ui_body["inspector_proxy_token"] == "am-local-inspector"
        assert "MCP_PROXY_AUTH_TOKEN=am-local-inspector" in ui_body["inspector_url"]
        assert "transport=sse" in ui_body["inspector_url"]
        assert "hub%3A8130%2Fsse" in ui_body["inspector_url"] or "hub:8130/sse" in ui_body[
            "inspector_url"
        ]
        assert ui_body.get("google_ui_url") == "/google/"
        g_insp = ui_body.get("google_inspector_url") or ""
        assert "streamable-http" in g_insp
        assert "google%2Fmcp" in g_insp or "google/mcp" in g_insp
        assert "MCP_PROXY_AUTH_TOKEN=am-local-inspector" in g_insp

        bare_bearer = await client.post(
            "/mcp",
            headers={"Authorization": "Bearer", "Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 0, "method": "ping"},
        )
        assert bare_bearer.status_code == 200
        assert bare_bearer.json()["result"] == {}

        integ = await client.get("/api/v1/integrations")
        assert integ.status_code == 200
        rows = integ.json()
        assert len(rows) >= 5
        assert {r["slug"] for r in rows} >= {
            "github",
            "vault",
            "litellm",
            "am-qa-agent",
            "am-tool-agent",
            "google-workspace",
        }

        patched = await client.patch(
            "/api/v1/integrations/vault",
            json={"enabled": True, "vault_path": "apps/data/dev/infra/vault-token"},
        )
        assert patched.status_code == 200
        assert patched.json()["vault_path"] == "apps/data/dev/infra/vault-token"

        market = await client.get("/api/v1/marketplace")
        assert market.status_code == 200
        market_body = market.json()
        assert market_body["counts"]["hub_integrations"] >= 6
        slugs = {i["slug"] for i in market_body["items"] if i["kind"] == "hub-integration"}
        assert "github" in slugs and "google-workspace" in slugs
        assert "MCP_PROXY_AUTH_TOKEN" in market_body["inspector_url"]

        mcp = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            },
        )
        assert mcp.status_code == 200
        body = mcp.json()
        names = {t["name"] for t in body["result"]["tools"]}
        assert "hub_status" in names
        assert "vault_health" in names
        assert "google_workspace_status" in names

        # Inspector Accept includes both; prefer JSON so the Inspector proxy stays up.
        mcp_both = await client.post(
            "/mcp",
            headers={"Accept": "application/json, text/event-stream"},
            json={
                "jsonrpc": "2.0",
                "id": 9,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert mcp_both.status_code == 200
        assert "json" in (mcp_both.headers.get("content-type") or "")
        assert mcp_both.json()["result"]["serverInfo"]["name"] == "am-mcp-hub"
        assert mcp_both.headers.get("mcp-session-id")

        prompts = await client.post(
            "/mcp",
            headers={"Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 10, "method": "prompts/list", "params": {}},
        )
        assert prompts.status_code == 200
        assert len(prompts.json()["result"]["prompts"]) >= 1

        ping = await client.post(
            "/mcp",
            headers={"Accept": "application/json"},
            json={"jsonrpc": "2.0", "id": 11, "method": "ping"},
        )
        assert ping.status_code == 200
        assert ping.json()["result"] == {}

        call = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "hub_status", "arguments": {}},
            },
        )
        assert call.status_code == 200
        text = call.json()["result"]["content"][0]["text"]
        assert "enabled" in text

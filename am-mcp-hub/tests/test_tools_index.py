from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.core import database as dbmod
from am_mcp_hub.main import app
from am_mcp_hub.services.catalog import EnabledIntegration
from am_mcp_hub.services.tools_index import build_tools_index, hub_callable_tool_names


def _write_inspect(asrax: Path) -> None:
    report = {
        "ok": 1,
        "total": 1,
        "ms": 10,
        "results": [
            {
                "name": "zoho",
                "ok": True,
                "tools": 2,
                "server": "zoho",
                "error": "",
                "tool_names": ["ZohoMail_getMailAccounts", "hub_status"],
            }
        ],
    }
    (asrax / "mcp-inspect-all-report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )


@pytest.fixture(autouse=True)
def _sqlite_and_asrax(tmp_path, monkeypatch):
    db_path = tmp_path / "hub.db"
    asrax = tmp_path / "asrax"
    asrax.mkdir()
    (asrax / "bin").mkdir()
    (asrax / "bin" / "zoho-mcp.cmd").write_text("@echo off\n", encoding="utf-8")
    _write_inspect(asrax)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("HUB_DEV_BYPASS_AUTH", "1")
    monkeypatch.setenv("LAPTOP_ASRAX_DIR", str(asrax))
    monkeypatch.setenv("LAPTOP_AM_DIR", str(tmp_path / "am"))
    monkeypatch.setenv("LOCAL_CREDS_DIR", str(tmp_path / "creds"))
    (tmp_path / "creds").mkdir(exist_ok=True)
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None
    yield
    get_settings.cache_clear()
    dbmod._engine = None
    dbmod._session_factory = None


def test_hub_callable_includes_core():
    names = hub_callable_tool_names([])
    assert "hub_status" in names
    assert "catalog_overview" in names


def test_build_tools_index_marks_hub_and_host(tmp_path, monkeypatch):
    asrax = Path(get_settings().laptop_asrax_dir)
    assert asrax.is_dir()
    settings = get_settings()
    integ = EnabledIntegration(
        slug="github",
        display_name="GitHub",
        adapter_type="github",
        description="",
        enabled=True,
        vault_path=None,
        settings={},
    )
    out = build_tools_index([integ], settings, scope="all", limit=500)
    tools = {(r["mcp"], r["tool"], r["callable"]) for r in out["items"]}
    assert ("hub", "hub_status", "hub") in tools
    assert ("zoho", "ZohoMail_getMailAccounts", "host") in tools
    # hub_status also appears under zoho inspect names but callable stays hub
    zoho_hub = [r for r in out["items"] if r["mcp"] == "zoho" and r["tool"] == "hub_status"]
    assert zoho_hub and zoho_hub[0]["callable"] == "hub"
    hub_only = build_tools_index([integ], settings, scope="hub")
    assert all(r["callable"] == "hub" for r in hub_only["items"])
    host_only = build_tools_index([integ], settings, scope="host")
    assert all(r["callable"] == "host" for r in host_only["items"])
    filtered = build_tools_index([integ], settings, mcp="zoho")
    assert filtered["items"] and all(r["mcp"] == "zoho" for r in filtered["items"])
    assert any(c["mcp"] == "zoho" for c in out["categories"])


@pytest.mark.asyncio
async def test_tools_index_api_and_openapi():
    from am_mcp_hub.core.database import init_db

    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/tools-index?scope=hub&limit=50")
        assert res.status_code == 200
        body = res.json()
        assert body["privacy"] == "laptop-local"
        assert body["scope"] == "hub"
        assert "counts" in body
        assert all(i["callable"] == "hub" for i in body["items"])
        home = await client.get("/api/v1/home-summary")
        assert home.status_code == 200
        links = home.json()["links"]
        assert links["tools"].startswith("/tools/")
        assert links["tools_hub"] == "/tools/?scope=hub"
        spec = (await client.get("/openapi.json")).json()
        assert "/api/v1/tools-index" in spec["paths"]
        params = {
            p["name"] for p in spec["paths"]["/api/v1/tools-index"]["get"].get("parameters", [])
        }
        assert {"q", "mcp", "scope", "kind", "limit", "offset"} <= params

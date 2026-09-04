from __future__ import annotations

from pathlib import Path

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services.catalog import EnabledIntegration
from am_mcp_hub.services.marketplace import build_marketplace


def test_marketplace_merges_integrations_and_launchers(tmp_path: Path, monkeypatch):
    asrax = tmp_path / "asrax"
    (asrax / "bin").mkdir(parents=True)
    (asrax / "bin" / "zoho-mcp.cmd").write_text("@echo off\n", encoding="utf-8")
    creds = tmp_path / "creds"
    creds.mkdir()
    monkeypatch.setenv("LOCAL_CREDS_DIR", str(creds))

    settings = HubSettings(
        laptop_asrax_dir=str(asrax),
        laptop_am_dir=str(tmp_path / "am"),
        local_creds_dir=str(creds),
        inspector_proxy_auth_token="am-local-inspector",
        inspector_mcp_url="http://hub:8130/sse",
    )
    integrations = [
        EnabledIntegration(
            slug="github",
            display_name="GitHub",
            adapter_type="github",
            description="gh",
            enabled=True,
            vault_path=None,
            settings={},
        )
    ]
    out = build_marketplace(integrations, settings)
    assert out["counts"]["hub_integrations"] == 1
    assert out["counts"]["stdio_launchers"] >= 1
    assert any(i["slug"] == "zoho" for i in out["items"] if i["kind"] == "stdio-launcher")
    assert "am-local-inspector" in out["inspector_url"]
    gh = next(i for i in out["items"] if i["slug"] == "github")
    assert any(t["name"] == "github_whoami" for t in gh["tools"])
    assert out["hub_core_tools"]
    assert "List Tools" in out["inspector_tools_hint"]
    assert "results" not in (out.get("inspect_report") or {})
    assert "present" in (out.get("inspect_report") or {})

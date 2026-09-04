from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from am_mcp_hub.adapters.registry import build_tools
from am_mcp_hub.core.config import get_settings
from am_mcp_hub.services import local_creds as creds
from am_mcp_hub.services.catalog import EnabledIntegration


def test_resolve_env_secret_reads_home_asrax(tmp_path: Path, monkeypatch):
    asrax = tmp_path / ".asrax"
    asrax.mkdir()
    (asrax / "credentials.env").write_text("GITHUB_TOKEN=ghp_test_resolve\n", encoding="utf-8")
    monkeypatch.setenv("LOCAL_CREDS_DIR", str(tmp_path / "creds"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_PERSONAL_ACCESS_TOKEN", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(creds.Path, "home", classmethod(lambda cls: tmp_path))
    assert creds.resolve_env_secret("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN") == "ghp_test_resolve"
    get_settings.cache_clear()


def test_github_whoami_uses_env_token_without_args(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LOCAL_CREDS_DIR", str(tmp_path / "creds"))
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    get_settings.cache_clear()
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
    tools = asyncio.get_event_loop().run_until_complete(build_tools(integrations))
    whoami = next(t for t in tools if t["name"] == "github_whoami")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {"login": "tester"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.get.return_value = mock_resp

    with patch("am_mcp_hub.adapters.registry.httpx.AsyncClient", return_value=mock_client):
        out = asyncio.get_event_loop().run_until_complete(whoami["handler"]({}))

    assert out["ok"] is True
    assert out["body"]["login"] == "tester"
    headers = mock_client.get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer ghp_from_env"
    get_settings.cache_clear()

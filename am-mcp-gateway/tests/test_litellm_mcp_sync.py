"""Tests for LiteLLM MCP manifest sync helpers."""
from pathlib import Path

from app.tools.litellm_mcp_sync import (
    build_allowed_tools_from_manifests,
    discover_manifests,
    prefixed_tool_name,
    repo_root_from_gateway,
)


def test_prefixed_tool_name():
    assert prefixed_tool_name("am_mcp_gateway", "run_modern_ui_auth_test") == (
        "am_mcp_gateway-run_modern_ui_auth_test"
    )


def test_discover_modern_ui_manifest():
    gateway_root = Path(__file__).resolve().parents[1]
    repo_root = repo_root_from_gateway(gateway_root)
    manifests = discover_manifests(repo_root)
    assert any("am-modern-ui" in str(p) for p in manifests)


def test_build_allowed_tools_from_manifest():
    gateway_root = Path(__file__).resolve().parents[1]
    repo_root = repo_root_from_gateway(gateway_root)
    manifests = discover_manifests(repo_root)
    allowed, descriptions = build_allowed_tools_from_manifests(manifests)
    assert "am_mcp_gateway-run_modern_ui_auth_test" in allowed
    assert descriptions["am_mcp_gateway-run_modern_ui_auth_test"]

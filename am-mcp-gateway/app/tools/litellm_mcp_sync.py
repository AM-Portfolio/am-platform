"""Build LiteLLM MCP server payload from am-*/testing/manifest.json files."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "am-ui-test-manifest/v1"
DEFAULT_SERVER_ALIAS = "am_mcp_gateway"
TOOL_PREFIX_SEPARATOR = "-"


def repo_root_from_gateway(gateway_root: Path) -> Path:
    """am-platform/am-mcp-gateway → AM-Portfolio-grp root."""
    return gateway_root.resolve().parents[1]


def discover_manifests(repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for candidate in sorted(repo_root.glob("am-*/testing/manifest.json")):
        if candidate.is_file():
            paths.append(candidate)
    return paths


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"Unsupported manifest schema in {path}")
    return data


def prefixed_tool_name(server_alias: str, operation_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "_", operation_id).lower()
    alias = server_alias.replace(" ", "_")
    return f"{alias}{TOOL_PREFIX_SEPARATOR}{safe}"


def build_allowed_tools_from_manifests(
    manifest_paths: list[Path],
    *,
    server_alias: str = DEFAULT_SERVER_ALIAS,
) -> tuple[list[str], dict[str, str]]:
    """Return (allowed_tools, tool_name_to_description) for LiteLLM MCP server."""
    allowed: list[str] = []
    descriptions: dict[str, str] = {}

    for path in manifest_paths:
        manifest = load_manifest(path)
        for tool in manifest.get("tools") or []:
            litellm_meta = tool.get("litellm") or {}
            operation_id = litellm_meta.get("operation_id") or tool.get("name")
            if not operation_id:
                continue
            prefixed = prefixed_tool_name(server_alias, operation_id)
            allowed.append(prefixed)
            desc = tool.get("description") or f"UI test tool from {path.parent.parent.name}"
            descriptions[prefixed] = desc

    # Stable order for config diffs
    allowed = sorted(set(allowed))
    return allowed, descriptions


def build_mcp_server_payload(
    *,
    gateway_base_url: str,
    manifest_paths: list[Path],
    server_alias: str = DEFAULT_SERVER_ALIAS,
    allow_all_keys: bool = True,
) -> dict[str, Any]:
    base = gateway_base_url.rstrip("/")
    allowed_tools, tool_name_to_description = build_allowed_tools_from_manifests(
        manifest_paths, server_alias=server_alias
    )
    return {
        "server_name": server_alias,
        "alias": server_alias,
        "description": "AM MCP Gateway — UI test tools from module testing manifests",
        "transport": "http",
        "url": base,
        "spec_path": f"{base}/openapi.json",
        "allow_all_keys": allow_all_keys,
        "allowed_tools": allowed_tools,
        "tool_name_to_description": tool_name_to_description,
    }

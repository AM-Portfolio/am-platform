"""Static tool metadata for Marketplace cards (no live MCP call)."""

from __future__ import annotations

from typing import Any

_CORE: tuple[dict[str, str], ...] = (
    {"name": "hub_status", "description": "Enabled integrations + Vault ref status"},
    {"name": "catalog_overview", "description": "Counts for skills/agents/rules/launchers"},
    {"name": "list_skills", "description": "List SKILL.md entries from laptop mounts"},
    {"name": "get_skill", "description": "Read one skill by name"},
    {"name": "list_agents", "description": "List agent markdown files"},
    {"name": "get_agent", "description": "Read one agent file"},
    {"name": "list_rules", "description": "List Cursor rules"},
    {"name": "list_mcp_launchers", "description": "List host *-mcp.cmd launchers"},
    {"name": "task_list", "description": "List asrax work tasks"},
    {"name": "task_get", "description": "Get one task"},
    {"name": "task_claim", "description": "Claim a task phase"},
    {"name": "task_add_step", "description": "Append task timeline step"},
    {"name": "task_set_analysis", "description": "Update task analysis"},
    {"name": "task_complete_phase", "description": "Complete a pipeline phase"},
    {"name": "task_complete", "description": "Complete a task"},
)

_BY_ADAPTER: dict[str, tuple[dict[str, str], ...]] = {
    "github": (
        {"name": "github_whoami", "description": "GitHub /user (token arg)"},
    ),
    "vault": (
        {"name": "vault_health", "description": "Vault sys/health"},
    ),
    "litellm": (
        {"name": "litellm_list_models", "description": "List LiteLLM models"},
    ),
    "qa_agent": (
        {"name": "qa_agent_health", "description": "QA agent /health"},
    ),
    "tool_agent": (
        {"name": "tool_agent_health", "description": "Tool agent /health"},
    ),
    "google_workspace": (
        {
            "name": "google_workspace_status",
            "description": "Upstream workspace-mcp health",
        },
        {
            "name": "google_workspace_list_tools",
            "description": "List tools from Google Workspace MCP",
        },
        {
            "name": "google_workspace_call_tool",
            "description": "Call a Google Workspace MCP tool by name",
        },
    ),
}


def hub_core_tools() -> list[dict[str, str]]:
    return [dict(t) for t in _CORE]


def tools_for_adapter(adapter_type: str) -> list[dict[str, str]]:
    rows = _BY_ADAPTER.get(adapter_type) or ()
    return [dict(t) for t in rows]


def marketplace_tools_for_integration(
    *,
    adapter_type: str,
    include_core: bool = False,
) -> list[dict[str, str]]:
    tools: list[dict[str, str]] = []
    if include_core:
        tools.extend(hub_core_tools())
    tools.extend(tools_for_adapter(adapter_type))
    return tools

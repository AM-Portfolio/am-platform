"""Named OpenAPI models + examples for hub admin UI APIs (flat JSON shapes)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChatSourceCount(BaseModel):
    source: str = Field(examples=["cursor"])
    count: int = Field(examples=[120])


class ChatListItem(BaseModel):
    id: str = Field(examples=["c1"])
    source: str = Field(examples=["cursor"])
    profile_id: str = Field(examples=["default"])
    machine_id: str = Field(examples=["laptop"])
    title: str = Field(examples=["Fix hub latency"])
    preview: str = Field(examples=["Fix hub latency"])
    updated_at: str | None = Field(default=None, examples=["2026-08-10T12:00:00Z"])
    created_at: str | None = Field(default=None, examples=["2026-08-09T09:00:00Z"])
    message_count: int | None = None


class ChatListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "chat_memory_root": "/laptop-asrax/chat-memory",
                    "items": [
                        {
                            "id": "c1",
                            "source": "cursor",
                            "profile_id": "default",
                            "machine_id": "laptop",
                            "title": "Fix hub latency",
                            "preview": "Fix hub latency",
                            "updated_at": "2026-08-10T12:00:00Z",
                            "created_at": "2026-08-09T09:00:00Z",
                        }
                    ],
                    "sources": [{"source": "cursor", "count": 120}],
                    "limit": 50,
                    "offset": 0,
                }
            ]
        }
    )

    chat_memory_root: str
    items: list[ChatListItem]
    sources: list[ChatSourceCount] | None = None
    limit: int = 50
    offset: int = 0


class AsraxSkillListItem(BaseModel):
    name: str = Field(examples=["am-code-review"])
    path: str = Field(examples=["/laptop-asrax/skills/am-code-review/SKILL.md"])
    home: str = Field(examples=["/laptop-asrax"])
    description: str | None = Field(default=None, examples=["Senior-style code review"])
    owner: str | None = None
    tags: list[str] | None = None
    mtime: float | None = None
    uri: str = Field(examples=["skill://am-code-review"])


class AsraxSkillsListResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "skills": [
                        {
                            "name": "am-code-review",
                            "path": "/laptop-asrax/skills/am-code-review/SKILL.md",
                            "home": "/laptop-asrax",
                            "description": "Senior-style code review",
                            "uri": "skill://am-code-review",
                        }
                    ]
                }
            ]
        }
    )

    skills: list[AsraxSkillListItem]
    privacy: str | None = "laptop-local"


class AsraxRelListItem(BaseModel):
    name: str = Field(examples=["reviewer"])
    rel: str = Field(examples=["reviewer.md"])
    path: str = Field(examples=["/laptop-asrax/agents/reviewer.md"])
    home: str = Field(examples=["/laptop-asrax"])
    description: str | None = None
    preview: str | None = None
    owner: str | None = None
    always_apply: bool | None = None
    readonly: bool | None = None
    profile_hint: str | None = None
    mtime: float | None = None
    uri: str | None = None


class AsraxRulesListResponse(BaseModel):
    rules: list[AsraxRelListItem]
    privacy: str | None = "laptop-local"


class AsraxAgentsListResponse(BaseModel):
    agents: list[AsraxRelListItem]
    privacy: str | None = "laptop-local"


class AsraxHookListItem(BaseModel):
    name: str = Field(examples=["pre-commit.py"])
    path: str = Field(examples=["/laptop-asrax/hooks/pre-commit.py"])
    home: str = Field(examples=["/laptop-asrax"])
    description: str | None = None
    preview: str | None = None
    kind: str | None = None
    mtime: float | None = None


class AsraxHooksListResponse(BaseModel):
    hooks: list[AsraxHookListItem]
    privacy: str | None = "laptop-local"


class CatalogWriteBase(BaseModel):
    force: bool = False
    expected_mtime: float | None = None


class SkillWriteRequest(CatalogWriteBase):
    name: str | None = None
    description: str | None = None
    owner: str | None = None
    body: str = ""
    raw: str | None = None


class RuleWriteRequest(CatalogWriteBase):
    rel: str | None = None
    description: str | None = None
    always_apply: bool | None = None
    globs: str | None = None
    body: str = ""
    raw: str | None = None


class HookWriteRequest(CatalogWriteBase):
    name: str | None = None
    content: str = ""


class AgentWriteRequest(CatalogWriteBase):
    rel: str | None = None
    body: str = ""


class ProfilePack(BaseModel):
    id: str
    label: str
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    rules_mode: str = "catalog"
    model_hint: str = Field(
        default="small",
        description="Suggested context size hint only; does not change IDE model",
    )
    agents_default: list[str] = Field(default_factory=list)
    skills_missing: list[str] = Field(default_factory=list)
    tools_missing: list[str] = Field(default_factory=list)
    privacy: str = "laptop-local"


class ProfilesListResponse(BaseModel):
    profiles: list[ProfilePack]
    privacy: str = "laptop-local"


class AgentBinding(BaseModel):
    agent: str
    profile: str = ""
    skills_add: list[str] = Field(default_factory=list)
    skills_drop: list[str] = Field(default_factory=list)
    tools_add: list[str] = Field(default_factory=list)
    tools_drop: list[str] = Field(default_factory=list)
    rules_mode: str = "inherit"
    notes: str = ""
    privacy: str = "laptop-local"


class SeedBindingsRequest(BaseModel):
    force: bool = False


class TaskCreateRequest(BaseModel):
    title: str
    body: str = ""
    assignee_type: str = "role"
    assignee_id: str = "developer"
    connection_id: str = ""


class TaskPatchRequest(BaseModel):
    title: str | None = None
    body: str | None = None
    assignee_type: str | None = None
    assignee_id: str | None = None
    connection_id: str | None = None
    status: str | None = None
    phase: str | None = None


class TaskStepRequest(BaseModel):
    kind: str = "note"
    title: str
    detail: str = ""
    tool_name: str = ""
    ok: bool | None = None
    connection_id: str = ""
    provider_kind: str = ""


class TaskAssignRunRequest(BaseModel):
    connection_id: str = ""


class TaskAnalysisRequest(BaseModel):
    suggested_agent: str = ""
    suggested_profile: str = ""
    rationale: str = ""


class TaskCompletePhaseRequest(BaseModel):
    phase: str
    ok: bool = True
    summary: str = ""


class TaskCompleteRequest(BaseModel):
    summary: str = ""
    ok: bool = True


class ConnectionUpsertRequest(BaseModel):
    id: str
    label: str = ""
    kind: str
    ide: str = ""
    cwd: str = ""
    base_url: str = ""
    model: str = ""
    auth_env: str = ""
    mcp_url: str = "http://127.0.0.1:8130/mcp"
    make_default: bool = False


class McpEnvCell(BaseModel):
    enabled: bool = False
    write: bool = False


class McpEnvAccessPut(BaseModel):
    active_env: str = "dev"
    matrix: dict[str, dict[str, McpEnvCell]] = Field(default_factory=dict)
    apply_active: bool = True


class LocalIdeTarget(BaseModel):
    id: str = Field(examples=["cursor"])
    label: str = Field(examples=["Cursor"])
    detected: bool = True
    server_count: int = 0
    local: bool = True
    path: str = ""


class HomeMarketplaceCounts(BaseModel):
    total: int | None = None
    hub_integrations: int | None = None
    stdio_launchers: int | None = None
    connected: int | None = None
    disconnected: int | None = None
    unknown: int | None = None
    configured: int | None = None
    hub_tools: int | None = None
    probed_tools: int | None = None
    probe_ok: int | None = None
    needs_config: int | None = None
    in_ide: int | None = None


class HomeInspectSlim(BaseModel):
    present: bool = False
    path: str | None = None
    ok: int | None = None
    total: int | None = None
    ms: int | None = None


class HomeMarketplaceSummary(BaseModel):
    counts: HomeMarketplaceCounts
    inspect_report: HomeInspectSlim
    ide_helper: bool | None = None
    ide_sync_hint: str | None = None
    local_ide_targets: list[LocalIdeTarget] | None = None


class HomeChatRecent(BaseModel):
    id: str | None = None
    title: str | None = None
    source: str | None = None
    profile_id: str | None = None
    updated_at: str | None = None
    created_at: str | None = None


class HomeChatSummary(BaseModel):
    total: int = 0
    chat_memory_root: str
    sources: list[ChatSourceCount]
    recent: list[HomeChatRecent]


class HomeAsraxSummary(BaseModel):
    counts: dict[str, int]
    homes: list[str]


class HomeLinks(BaseModel):
    marketplace: str = "/marketplace/"
    history: str = "/history/"
    skills: str = "/skills/"
    rules: str = "/rules/"
    hooks: str = "/hooks/"
    agents: str = "/agents/"
    catalog: str = "/catalog/"
    google: str = "/google/"
    tools: str = "/tools/?scope=all"
    tools_hub: str = "/tools/?scope=hub"
    inspector_url: str = "http://127.0.0.1:6274/"


class HomeSummaryResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "hub": {"ok": True},
                    "google": {"oauth_configured": True, "upstream_ok": True},
                    "asrax": {
                        "counts": {"skills": 21, "rules": 4, "hooks": 3, "agents": 5},
                        "homes": ["/laptop-asrax"],
                    },
                    "marketplace": {
                        "counts": {
                            "total": 40,
                            "connected": 28,
                            "disconnected": 4,
                            "unknown": 8,
                            "configured": 35,
                            "needs_config": 2,
                            "hub_tools": 12,
                            "probed_tools": 90,
                            "in_ide": 20,
                        },
                        "inspect_report": {
                            "present": True,
                            "path": "/laptop-asrax/inspect.json",
                            "ok": 28,
                            "total": 40,
                            "ms": 1200,
                        },
                        "ide_helper": True,
                        "ide_sync_hint": None,
                        "local_ide_targets": [
                            {
                                "id": "cursor",
                                "label": "Cursor",
                                "detected": True,
                                "server_count": 12,
                                "local": True,
                                "path": "C:/Users/me/.cursor/mcp.json",
                            }
                        ],
                    },
                    "chat": {
                        "total": 269,
                        "chat_memory_root": "/laptop-asrax/chat-memory",
                        "sources": [{"source": "cursor", "count": 120}],
                        "recent": [
                            {
                                "id": "c1",
                                "title": "Fix hub latency",
                                "source": "cursor",
                                "profile_id": "default",
                                "updated_at": "2026-08-10T12:00:00Z",
                            }
                        ],
                    },
                    "links": {
                        "marketplace": "/marketplace/",
                        "history": "/history/",
                        "skills": "/skills/",
                        "rules": "/rules/",
                        "hooks": "/hooks/",
                        "agents": "/agents/",
                        "catalog": "/catalog/",
                        "google": "/google/",
                        "tools": "/tools/?scope=all",
                        "tools_hub": "/tools/?scope=hub",
                        "inspector_url": "http://127.0.0.1:6274/",
                    },
                    "privacy": "laptop-local",
                }
            ]
        }
    )

    hub: dict[str, Any]
    google: dict[str, Any]
    asrax: HomeAsraxSummary
    marketplace: HomeMarketplaceSummary
    chat: HomeChatSummary
    links: HomeLinks
    privacy: str = "laptop-local"


class MarketplaceMcpSyncRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"force": False, "ides": ["cursor", "claude"], "scope": "local"}
            ]
        }
    )

    force: bool = False
    ides: list[str] = Field(default_factory=list, examples=[["cursor", "claude"]])
    scope: str = "local"


class MarketplaceMcpSyncTarget(BaseModel):
    ide: str | None = None
    skipped_target: bool | None = None
    path: str | None = None
    error: str | None = None


class MarketplaceMcpSyncResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "ok": True,
                    "desired": ["asrax", "github"],
                    "targets": [
                        {
                            "ide": "cursor",
                            "skipped_target": False,
                            "path": "C:/Users/me/.cursor/mcp.json",
                        }
                    ],
                }
            ]
        }
    )

    ok: bool | None = None
    error: str | None = None
    desired: list[str] | None = None
    servers: list[str] | None = None
    targets: list[MarketplaceMcpSyncTarget] | None = None


class ToolsIndexItem(BaseModel):
    mcp: str = Field(examples=["hub"])
    tool: str = Field(examples=["hub_status"])
    ok: bool | None = True
    kind: str = Field(examples=["hub-integration"])
    configured: bool = True
    needs_config: bool = False
    slug: str = Field(examples=["hub"])
    callable: str = Field(examples=["hub"], description="hub = call via /mcp; host = configure only")
    description: str = ""


class ToolsIndexCategory(BaseModel):
    mcp: str = Field(examples=["zoho"])
    count: int = Field(examples=[42])


class ToolsIndexCounts(BaseModel):
    total: int = 0
    filtered: int = 0
    hub: int = 0
    host: int = 0
    mcps: int = 0
    returned: int = 0


class ToolsIndexResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "items": [
                        {
                            "mcp": "hub",
                            "tool": "hub_status",
                            "ok": True,
                            "kind": "hub-integration",
                            "configured": True,
                            "needs_config": False,
                            "slug": "hub",
                            "callable": "hub",
                            "description": "Enabled integrations + Vault ref status",
                        },
                        {
                            "mcp": "zoho",
                            "tool": "ZohoMail_getMailAccounts",
                            "ok": True,
                            "kind": "stdio-launcher",
                            "configured": True,
                            "needs_config": False,
                            "slug": "zoho",
                            "callable": "host",
                            "description": "",
                        },
                    ],
                    "categories": [{"mcp": "hub", "count": 12}, {"mcp": "zoho", "count": 42}],
                    "counts": {
                        "total": 600,
                        "filtered": 54,
                        "hub": 12,
                        "host": 588,
                        "mcps": 40,
                        "returned": 2,
                    },
                    "limit": 500,
                    "offset": 0,
                    "scope": "all",
                    "inspect_present": True,
                    "privacy": "laptop-local",
                }
            ]
        }
    )

    items: list[ToolsIndexItem]
    categories: list[ToolsIndexCategory]
    counts: ToolsIndexCounts
    limit: int = 500
    offset: int = 0
    scope: str = "all"
    inspect_present: bool = False
    privacy: str = "laptop-local"

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class HubSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    app_port: int = 8130
    log_level: str = "INFO"

    # sqlite+aiosqlite:///./mcp_hub.db for laptop; postgres for prod
    database_url: str = "sqlite+aiosqlite:///./mcp_hub.db"

    default_org_slug: str = "asrax"
    default_org_name: str = "Asrax"

    identity_url: str = "https://am.asrax.in/identity"
    # When set, Bearer tokens are accepted if they match (local/dev only).
    hub_dev_bypass_auth: bool = False
    hub_admin_token: str = ""
    # JSON map of email|subject -> roles list.
    # Roles: platform_admin, viewer, env_writer:dev|preprod|prod
    # Example: {"you@asrax.in":["platform_admin"],"dev@asrax.in":["env_writer:dev","viewer"]}
    hub_role_map: str = "{}"

    litellm_url: str = "https://litellm.munish.org"
    litellm_master_key: str = ""
    vault_addr: str = "https://vault.asrax.in"
    qa_agent_base_url: str = "https://am-dev.asrax.in/qa"
    tool_agent_base_url: str = "https://am-dev.asrax.in/tools"
    # workspace-mcp Streamable HTTP (docker-compose publishes :8000)
    google_workspace_mcp_url: str = "http://127.0.0.1:8000/mcp"
    # Host-facing URL for Inspector / Cursor (prefer hub proxy)
    google_workspace_mcp_public_url: str = "http://127.0.0.1:8130/google/mcp"
    # Public origin+prefix for SSE endpoint events (e.g. https://am-dev.asrax.in/hub)
    public_base_url: str = ""
    # Official MCP Inspector UI (compose service or local npx)
    inspector_public_url: str = "http://127.0.0.1:6274/"
    # Must match inspector service MCP_PROXY_AUTH_TOKEN (local compose only).
    inspector_proxy_auth_token: str = "am-local-inspector"
    # Host-persisted credentials (bind-mount). Never leave this machine via hub APIs.
    local_creds_dir: str = "./local-data/credentials"
    # Mounted laptop homes (compose: ~/.asrax + ~/.am) for skills/agents/rules/MCP launchers.
    laptop_asrax_dir: str = "/laptop-asrax"
    laptop_am_dir: str = "/laptop-am"
    # URL the Inspector proxy uses to reach hub MCP (docker DNS). Prefer classic SSE.
    inspector_mcp_url: str = "http://hub:8130/sse"
    # Optional host helper for live Marketplace/Catalog refresh (am ai probe-server).
    host_probe_url: str = "http://host.docker.internal:8765"


@lru_cache
def get_settings() -> HubSettings:
    return HubSettings()

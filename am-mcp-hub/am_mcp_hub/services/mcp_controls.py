"""MCP on/off + write/read controls stored in local credentials."""

from __future__ import annotations

import re
from typing import Any

from am_mcp_hub.services import local_creds as creds

_CONTROLS_FILE = "credentials.d/mcp-controls.env"

_WRITE_KEY_ALIASES: dict[str, str] = {
    "grafana": "AM_GRAFANA_MCP_WRITE",
    "linkedin": "AM_LINKEDIN_MCP_WRITE",
    "linkedin-profiles": "AM_LINKEDIN_MCP_WRITE",
    "cloudflare": "AM_CLOUDFLARE_MCP_WRITE",
    "argocd": "AM_ARGOCD_MCP_WRITE",
    "gmail": "AM_GMAIL_MCP_WRITE",
    "google-drive": "AM_GOOGLE_DRIVE_MCP_WRITE",
    "youtube": "AM_YOUTUBE_MCP_WRITE",
    "meta": "AM_META_MCP_WRITE",
    "ewaybill": "AM_EWB_MCP_WRITE",
    "gstr": "AM_GSTR_MCP_WRITE",
    "am-engage": "AM_ENGAGE_MCP_WRITE",
    "am-qa-agent": "AM_QA_AGENT_MCP_WRITE",
    "am-tool-agent": "AM_TOOL_AGENT_MCP_WRITE",
    "am-support-agent": "AM_SUPPORT_AGENT_MCP_WRITE",
    "temporal": "AM_TEMPORAL_MCP_WRITE",
    "litellm": "AM_LITELLM_MCP_WRITE",
    "kafka": "AM_KAFKA_MCP_WRITE",
    "keycloak": "AM_KEYCLOAK_MCP_WRITE",
    "minio": "AM_MINIO_MCP_WRITE",
    "subscription": "AM_SUBSCRIPTION_MCP_WRITE",
    "zoho-cliq": "AM_ZOHO_CLIQ_MCP_WRITE",
}


def write_env_key(slug: str) -> str:
    alias = _WRITE_KEY_ALIASES.get(slug)
    if alias:
        return alias
    token = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_").upper()
    return f"AM_{token}_MCP_WRITE"


def enabled_env_key(slug: str) -> str:
    token = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_").upper()
    return f"MCP_ON_{token}"


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def merged_env() -> dict[str, str]:
    """Best-effort merge of env currently loaded into the hub process."""
    # Prefer live environ (load_into_environ already merged laptop + local creds).
    return {k: str(v) for k, v in __import__("os").environ.items() if v is not None}


def controls_for_slug(slug: str, *, hub_enabled: bool | None = None) -> dict[str, Any]:
    env = merged_env()
    write_key = write_env_key(slug)
    on_key = enabled_env_key(slug)
    write_enabled = _truthy(env.get(write_key))
    if hub_enabled is None:
        enabled = _truthy(env.get(on_key)) if on_key in env else True
    else:
        enabled = bool(hub_enabled)
    return {
        "enabled": enabled,
        "write_enabled": write_enabled,
        "write_key": write_key,
        "enabled_key": on_key,
        "config_mode": "edit" if write_enabled else "read",
    }


def upsert_env_key(rel: str, key: str, value: str) -> str:
    text = creds.read_file(rel)
    lines = text.splitlines() if text else []
    found = False
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        k = stripped.split("=", 1)[0].strip()
        if k == key:
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip():
            out.append("")
        out.append(f"{key}={value}")
    content = "\n".join(out).rstrip() + "\n"
    creds.write_file(rel, content)
    return rel


def set_write_enabled(slug: str, *, enabled: bool, cred_target: str | None) -> dict[str, Any]:
    import os

    key = write_env_key(slug)
    target = cred_target or _CONTROLS_FILE
    if not target.startswith("credentials"):
        target = _CONTROLS_FILE
    value = "1" if enabled else "0"
    upsert_env_key(target, key, value)
    # Also mirror into mcp-controls.env so toggles stay discoverable in one place.
    if target != _CONTROLS_FILE:
        upsert_env_key(_CONTROLS_FILE, key, value)
    creds.load_into_environ(override=True)
    os.environ[key] = value
    return controls_for_slug(slug)


def set_launcher_enabled(slug: str, *, enabled: bool) -> dict[str, Any]:
    import os

    key = enabled_env_key(slug)
    value = "1" if enabled else "0"
    upsert_env_key(_CONTROLS_FILE, key, value)
    creds.load_into_environ(override=True)
    os.environ[key] = value
    return controls_for_slug(slug, hub_enabled=enabled)

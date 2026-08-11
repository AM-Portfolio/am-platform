"""Google Workspace status for the hub /google/ UI (no secret values)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from am_mcp_hub.core.config import HubSettings, get_settings
from am_mcp_hub.services import local_creds as creds
from am_mcp_hub.services.marketplace import _google_inspector_url


def _oauth_configured(settings: HubSettings) -> dict[str, Any]:
    env_id = bool((os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip())
    env_secret = bool((os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip())
    file_paths = [
        Path(settings.local_creds_dir).expanduser() / "secrets" / "google-oauth-client.json",
        Path(os.environ.get("GOOGLE_OAUTH_CLIENT_FILE") or ""),
        Path(os.environ.get("GOOGLE_DRIVE_OAUTH_CREDENTIALS") or ""),
    ]
    file_ok = any(p.is_file() for p in file_paths if str(p))
    sample_ok = False
    try:
        text = creds.read_file(creds.default_target("google.env"))
        keys = creds.parse_env_keys(text)
        sample_ok = bool(
            (keys.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
            and (keys.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
        )
    except ValueError:
        sample_ok = False
    configured = (env_id and env_secret) or file_ok or sample_ok
    return {
        "configured": configured,
        "client_id_in_env": env_id,
        "client_secret_in_env": env_secret,
        "oauth_json_file_present": file_ok,
        "google_env_file_filled": sample_ok,
        "redirect_uri": os.environ.get("GOOGLE_OAUTH_REDIRECT_URI")
        or "http://127.0.0.1:8000/oauth2callback",
    }


async def google_status(
    settings: HubSettings | None = None,
    *,
    upstream_timeout: float = 8.0,
) -> dict[str, Any]:
    settings = settings or get_settings()
    upstream_mcp = settings.google_workspace_mcp_url.rstrip("/")
    base = upstream_mcp[: -len("/mcp")] if upstream_mcp.endswith("/mcp") else upstream_mcp
    health_url = f"{base}/health"
    oauth = _oauth_configured(settings)
    upstream: dict[str, Any] = {"ok": None, "url": health_url}
    try:
        async with httpx.AsyncClient(timeout=upstream_timeout) as client:
            resp = await client.get(health_url)
            upstream = {
                "ok": resp.status_code < 500,
                "status": resp.status_code,
                "url": health_url,
                "body": (resp.text or "")[:400],
            }
    except httpx.TimeoutException:
        upstream = {"ok": None, "url": health_url, "error": "timeout"}
    except httpx.HTTPError as exc:
        upstream = {"ok": False, "url": health_url, "error": str(exc)}

    return {
        "service": "google-workspace",
        "ui": "/google/",
        "public_mcp_url": settings.google_workspace_mcp_public_url
        or "http://127.0.0.1:8130/google/mcp",
        "upstream_mcp_url": upstream_mcp,
        "host_note": (
            "http://127.0.0.1:8000/ is workspace-mcp health JSON, not a product UI. "
            "Use /google/ on the hub."
        ),
        "upstream": upstream,
        "oauth": oauth,
        "google_inspector_url": _google_inspector_url(settings),
        "inspector_proxy_token": settings.inspector_proxy_auth_token,
        "tools_ui_url": "/tools/",
    }

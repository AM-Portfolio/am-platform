#!/usr/bin/env python3
"""
Register / update AM MCP Gateway UI test tools in LiteLLM via Management API.

Reads am-*/testing/manifest.json → sets allowed_tools on mcp_servers.am_mcp_gateway.

Usage:
  python scripts/sync_litellm_mcp_tools.py
  python scripts/sync_litellm_mcp_tools.py --dry-run
  python scripts/sync_litellm_mcp_tools.py --gateway-url http://localhost:8120
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.tools.litellm_mcp_sync import (  # noqa: E402
    DEFAULT_SERVER_ALIAS,
    build_mcp_server_payload,
    discover_manifests,
    repo_root_from_gateway,
)

DEFAULT_LITELLM = "http://localhost:4000"


def _auth_headers(master_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {master_key}", "Content-Type": "application/json"}


def _find_server(servers: list[dict], alias: str) -> dict | None:
    for row in servers:
        if row.get("alias") == alias or row.get("server_name") == alias:
            return row
    return None


def sync_to_litellm(
    *,
    litellm_base: str,
    master_key: str,
    gateway_base_url: str,
    server_alias: str,
    manifest_paths: list[Path],
    dry_run: bool,
) -> int:
    payload = build_mcp_server_payload(
        gateway_base_url=gateway_base_url,
        manifest_paths=manifest_paths,
        server_alias=server_alias,
    )

    if dry_run:
        print(json.dumps(payload, indent=2))
        return 0

    base = litellm_base.rstrip("/")
    headers = _auth_headers(master_key)

    with httpx.Client(timeout=60.0) as client:
        list_resp = client.get(f"{base}/v1/mcp/server", headers=headers)
        list_resp.raise_for_status()
        existing = _find_server(list_resp.json(), server_alias)

        if existing:
            update = {**payload, "server_id": existing["server_id"]}
            resp = client.put(f"{base}/v1/mcp/server", headers=headers, json=update)
            action = "updated"
        else:
            resp = client.post(f"{base}/v1/mcp/server", headers=headers, json=payload)
            action = "created"

        if resp.status_code >= 400:
            print(f"LiteLLM MCP sync failed [{resp.status_code}]: {resp.text[:800]}", file=sys.stderr)
            return 1

        body = resp.json()
        print(f"LiteLLM MCP server {action}: alias={server_alias} id={body.get('server_id', '?')}")
        print(f"  allowed_tools={payload['allowed_tools']}")
        print(f"  spec_path={payload['spec_path']}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync UI test MCP tools to LiteLLM")
    parser.add_argument("--litellm-url", default=os.getenv("LITELLM_BASE_URL", DEFAULT_LITELLM))
    parser.add_argument(
        "--master-key",
        default=os.getenv("LITELLM_MASTER_KEY"),
        help="LiteLLM PROXY_ADMIN key (required unless --dry-run)",
    )
    parser.add_argument(
        "--gateway-url",
        default=os.getenv("MCP_GATEWAY_PUBLIC_URL", "http://localhost:8120"),
    )
    parser.add_argument("--server-alias", default=os.getenv("LITELLM_MCP_SERVER_ALIAS", DEFAULT_SERVER_ALIAS))
    parser.add_argument("--repo-root", type=Path, default=None, help="Monorepo root (auto-detected)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root or repo_root_from_gateway(ROOT)
    manifests = discover_manifests(repo_root)
    if not manifests:
        print(f"No manifests under {repo_root}/am-*/testing/manifest.json", file=sys.stderr)
        return 1

    print(f"Repo root: {repo_root}")
    print(f"Manifests: {[str(p.relative_to(repo_root)) for p in manifests]}")

    if not args.dry_run and not args.master_key:
        print("LITELLM_MASTER_KEY required (or use --dry-run)", file=sys.stderr)
        return 1

    return sync_to_litellm(
        litellm_base=args.litellm_url,
        master_key=args.master_key or "",
        gateway_base_url=args.gateway_url,
        server_alias=args.server_alias,
        manifest_paths=manifests,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    raise SystemExit(main())

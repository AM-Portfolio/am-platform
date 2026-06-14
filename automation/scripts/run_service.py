#!/usr/bin/env python3
"""Run am-platform services locally (used by per-module package.json)."""
from __future__ import annotations

import subprocess
import sys

from platform_env import PLATFORM_ROOT, identity_env, notification_env, subscription_env, mcp_gateway_env
from uvicorn_runner import build_uvicorn_args


def run_uvicorn(module: str, *, reload: bool, env: dict[str, str], cwd_name: str) -> int:
    port = env.get("APP_PORT", "8113")
    args = build_uvicorn_args(module, port=port, reload=reload)
    print(f"\n>>> {' '.join(args)}\n", flush=True)
    return subprocess.run(args, cwd=PLATFORM_ROOT / cwd_name, env=env).returncode


def run_identity(*, reload: bool) -> int:
    return run_uvicorn(
        "am_identity.main:app",
        reload=reload,
        env=identity_env(),
        cwd_name="am-identity",
    )


def run_subscription(*, reload: bool) -> int:
    return run_uvicorn(
        "am_subscription.main:app",
        reload=reload,
        env=subscription_env(),
        cwd_name="am-subscription",
    )


def run_notification(*, reload: bool) -> int:
    return run_uvicorn(
        "am_notification.main:app",
        reload=reload,
        env=notification_env(),
        cwd_name="am-notification",
    )


def run_mcp_gateway(*, reload: bool) -> int:
    return run_uvicorn(
        "app.main:app",
        reload=reload,
        env=mcp_gateway_env(),
        cwd_name="am-mcp-gateway",
    )


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: run_service.py <identity|subscription|notification|mcp-gateway> <dev|preprod|prod>")
        sys.exit(1)

    service = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "dev"
    reload = mode == "dev"

    import os
    if "preprod" in mode:
        os.environ["APP_ENV"] = "preprod"
    elif "prod" in mode:
        os.environ["APP_ENV"] = "prod"

    if service == "identity":
        sys.exit(run_identity(reload=reload))
    if service == "subscription":
        sys.exit(run_subscription(reload=reload))
    if service == "notification":
        sys.exit(run_notification(reload=reload))
    if service == "mcp-gateway":
        sys.exit(run_mcp_gateway(reload=reload))

    print(f"Unknown service: {service}")
    sys.exit(1)



if __name__ == "__main__":
    main()

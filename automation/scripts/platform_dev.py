#!/usr/bin/env python3
"""
Root-level platform checks (orchestration only).
Per-module run/test/lint live in each workspace package.json.
"""
from __future__ import annotations

import sys

from platform_env import PLATFORM_ROOT, load_env_files, python_exe


def cmd_env_check() -> int:
    required = [
        "KEYCLOAK_URL",
        "KEYCLOAK_REALM",
        "OIDC_TOKEN_URL",
        "AM_IDENTITY_CLIENT_SECRET",
    ]
    env = load_env_files()
    missing = [key for key in required if not env.get(key) or env[key].startswith("<")]
    print(f"Platform root: {PLATFORM_ROOT}")
    print(f"Python: {python_exe()}")
    if missing:
        print("Missing or placeholder env keys:", ", ".join(missing))
        print("Set them in .secrets.env (see .env.example)")
        return 1
    print("Required env keys present.")
    return 0


def cmd_dev() -> int:
    mode = sys.argv[1]
    reload = mode != "dev:prod"
    from run_platform import run_platform

    return run_platform(reload=reload)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: platform_dev.py <env:check|dev|dev:prod>")
        sys.exit(1)
    command = sys.argv[1]
    if command == "env:check":
        sys.exit(cmd_env_check())
    if command in ("dev", "dev:prod"):
        sys.exit(cmd_dev())
    print(f"Unknown command: {sys.argv[1]}")
    sys.exit(1)


if __name__ == "__main__":
    main()

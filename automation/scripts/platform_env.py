"""Shared paths and env loading for am-platform dev scripts."""
from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PLATFORM_ROOT = SCRIPT_DIR.parent.parent
REPO_ROOT = PLATFORM_ROOT.parent

IDENTITY_LIB_PATHS = [
    PLATFORM_ROOT / "libraries" / "am-platform-common",
    PLATFORM_ROOT / "libraries" / "am-platform-security",
    PLATFORM_ROOT / "am-identity",
]

SUBSCRIPTION_LIB_PATHS = [
    PLATFORM_ROOT / "libraries" / "am-platform-common",
    PLATFORM_ROOT / "libraries" / "am-platform-security",
    PLATFORM_ROOT / "am-subscription",
]

NOTIFICATION_LIB_PATHS = [
    PLATFORM_ROOT / "libraries" / "am-platform-common",
    PLATFORM_ROOT / "libraries" / "am-platform-security",
    PLATFORM_ROOT / "am-notification",
]


def notification_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(load_env_files())
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in NOTIFICATION_LIB_PATHS)
    env["APP_NAME"] = "am-notification"
    env["APP_PORT"] = "8111"
    mongo_uri = env.get("AM_NOTIFICATION_MONGO_URI", "")
    if (not mongo_uri or mongo_uri.startswith("<")) and not env.get("AM_NOTIFICATION_MONGO_HOST"):
        env["AM_NOTIFICATION_MONGO_HOST"] = "mongodb.asrax.in"
        env.setdefault("AM_NOTIFICATION_MONGO_PORT", "8888")
    kafka_bootstrap = env.get("KAFKA_BOOTSTRAP_SERVERS", "")
    if ".svc.cluster.local" in kafka_bootstrap and not env.get("AM_NOTIFICATION_KAFKA_BOOTSTRAP_SERVERS"):
        env["AM_NOTIFICATION_KAFKA_BOOTSTRAP_SERVERS"] = "kafka.asrax.in:8890"
    return env


def python_exe() -> str:
    candidates = [
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
        PLATFORM_ROOT / ".venv" / "Scripts" / "python.exe",
        PLATFORM_ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def load_env_file(path: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    if not path.is_file():
        return merged
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        merged[key.strip()] = value.strip()
    return merged


def load_env_files(*, preprod: bool = False) -> dict[str, str]:
    merged: dict[str, str] = {}
    for name in (".env", ".secrets.env"):
        merged.update(load_env_file(PLATFORM_ROOT / name))
    if preprod or os.environ.get("AM_PLATFORM_ENV") == "preprod":
        preprod_path = (
            REPO_ROOT
            / "am-env-vault"
            / "am-env-vault"
            / "environments"
            / "preprod"
            / "am-platform__secrets.preprod.env"
        )
        merged.update(load_env_file(preprod_path))
    return merged


def identity_env(*, preprod: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    if preprod:
        env["AM_PLATFORM_ENV"] = "preprod"
    env.update(load_env_files(preprod=preprod))
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in IDENTITY_LIB_PATHS)
    env["APP_NAME"] = "am-identity"
    env["APP_PORT"] = "8113"
    env.setdefault("IDENTITY_VERIFY_SSL", "false")
    return env


def subscription_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(load_env_files())
    env["PYTHONPATH"] = os.pathsep.join(str(p) for p in SUBSCRIPTION_LIB_PATHS)
    env["APP_NAME"] = "am-subscription"
    env["APP_PORT"] = "8110"
    # Cluster DNS (e.g. postgresql.infra.svc.cluster.local) does not resolve on a dev laptop.
    pg_host = env.get("POSTGRES_HOST", "")
    if ".svc.cluster.local" in pg_host and not env.get("AM_SUBSCRIPTION_POSTGRES_HOST"):
        env["AM_SUBSCRIPTION_POSTGRES_HOST"] = "postgres.asrax.in"
        env.setdefault("AM_SUBSCRIPTION_POSTGRES_PORT", "8891")
    return env

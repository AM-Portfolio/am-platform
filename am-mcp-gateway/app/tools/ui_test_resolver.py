"""Resolve ui-test wrapper targets for MCP gateway tool proxy."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def resolve_env_refs(value: str, env: dict[str, str]) -> str:
    pattern = re.compile(r"\$\{([^}]+)\}")

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in env:
            raise KeyError(f"Missing env var for target ref: {key}")
        return env[key]

    return pattern.sub(repl, value)


def _resolve_obj(obj: Any, env: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return resolve_env_refs(obj, env) if "${" in obj else obj
    if isinstance(obj, dict):
        return {k: _resolve_obj(v, env) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_obj(v, env) for v in obj]
    return obj


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_module_target(
    manifest_path: Path,
    *,
    module: str,
    environment: str,
    target_name: str | None = None,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    modules = manifest.get("modules") or {}
    if module not in modules:
        raise KeyError(f"Unknown module {module!r} in manifest")

    mod = modules[module]
    repo_root = (manifest_path.parent / mod.get("repo_root", "..")).resolve()
    targets_path = repo_root / mod["targets_file"].format(environment=environment)
    env_path = repo_root / mod["env_file"].format(environment=environment)

    merged_env = dict(os.environ)
    merged_env.update(load_env_file(env_path))
    data = _resolve_obj(json.loads(targets_path.read_text(encoding="utf-8")), merged_env)

    name = target_name or data.get("default_target") or mod.get("default_target") or "main"
    targets = data.get("targets") or {}
    if name not in targets:
        raise KeyError(f"Target {name!r} not found in {targets_path}")

    entry = targets[name]
    return {
        "module": module,
        "environment": environment,
        "target": name,
        "target_url": entry["base_url"],
        "ui_mode": entry.get("ui_mode", name),
        "profile": entry.get("profile"),
        "auth_login_mode": entry.get("auth_login_mode", "demo"),
        "targets_file": str(targets_path),
        "env_file": str(env_path),
    }

"""Per-env MCP enabled/write matrix under ~/.asrax (laptop-local)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from am_mcp_hub.core.config import HubSettings
from am_mcp_hub.services import mcp_controls
from am_mcp_hub.services.catalog_write import _write_home
from am_mcp_hub.services.auth import ENVS

_PRIVACY = "laptop-local"
_MATRIX_REL = "credentials.d/mcp-env-access.json"


def _matrix_path(settings: HubSettings) -> Path:
    home = _write_home(settings)
    return home / "credentials.d" / "mcp-env-access.json"


def _empty_cell() -> dict[str, bool]:
    return {"enabled": False, "write": False}


def _normalize_cell(raw: Any) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return _empty_cell()
    return {
        "enabled": bool(raw.get("enabled")),
        "write": bool(raw.get("write") or raw.get("write_enabled")),
    }


def _normalize_matrix(raw: dict[str, Any] | None) -> dict[str, dict[str, dict[str, bool]]]:
    out: dict[str, dict[str, dict[str, bool]]] = {}
    if not isinstance(raw, dict):
        return out
    for slug, envs in raw.items():
        if not isinstance(slug, str) or not slug.strip():
            continue
        if not isinstance(envs, dict):
            continue
        row: dict[str, dict[str, bool]] = {e: _empty_cell() for e in ENVS}
        for env in ENVS:
            if env in envs:
                row[env] = _normalize_cell(envs.get(env))
        out[slug.strip()] = row
    return out


def read_access(settings: HubSettings) -> dict[str, Any]:
    path = _matrix_path(settings)
    active_env = "dev"
    matrix: dict[str, dict[str, dict[str, bool]]] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            env = str(data.get("active_env") or "dev").strip().lower()
            if env in ENVS:
                active_env = env
            matrix = _normalize_matrix(data.get("matrix") if isinstance(data.get("matrix"), dict) else data)
            # Support flat file that is only matrix
            if "matrix" not in data and "active_env" not in data:
                matrix = _normalize_matrix(data)
    return {
        "active_env": active_env,
        "envs": list(ENVS),
        "matrix": matrix,
        "privacy": _PRIVACY,
        "path": str(path),
        "host_path_hint": str(path).replace("/laptop-asrax", "~/.asrax"),
    }


def write_access(
    settings: HubSettings,
    *,
    matrix: dict[str, Any],
    active_env: str | None = None,
    apply_active: bool = True,
) -> dict[str, Any]:
    current = read_access(settings)
    env = (active_env or current["active_env"] or "dev").strip().lower()
    if env not in ENVS:
        env = "dev"
    normalized = _normalize_matrix(matrix)
    path = _matrix_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_env": env,
        "matrix": normalized,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if apply_active:
        apply_env_to_controls(settings, env, normalized)
    return read_access(settings)


def apply_env_to_controls(
    settings: HubSettings,
    env: str,
    matrix: dict[str, dict[str, dict[str, bool]]] | None = None,
) -> dict[str, Any]:
    """Mirror one env column into mcp-controls.env for IDE sync."""
    _ = settings
    want = env.strip().lower()
    if want not in ENVS:
        want = "dev"
    data = matrix if matrix is not None else read_access(settings)["matrix"]
    applied: list[str] = []
    for slug, envs in data.items():
        cell = envs.get(want) or _empty_cell()
        mcp_controls.set_launcher_enabled(slug, enabled=bool(cell.get("enabled")))
        mcp_controls.set_write_enabled(
            slug,
            enabled=bool(cell.get("write")),
            cred_target="credentials.d/mcp-controls.env",
        )
        applied.append(slug)
    # Persist active_env if matrix file exists / create stub
    path = _matrix_path(settings)
    existing = read_access(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"active_env": want, "matrix": existing["matrix"] if matrix is None else data},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"active_env": want, "applied_slugs": applied, "privacy": _PRIVACY}


def ensure_slugs(settings: HubSettings, slugs: list[str]) -> dict[str, Any]:
    """Ensure matrix rows exist for marketplace slugs (default all disabled)."""
    current = read_access(settings)
    matrix = dict(current["matrix"])
    changed = False
    for slug in slugs:
        s = (slug or "").strip()
        if not s or s in matrix:
            continue
        matrix[s] = {e: _empty_cell() for e in ENVS}
        changed = True
    if changed:
        return write_access(
            settings,
            matrix=matrix,
            active_env=current["active_env"],
            apply_active=False,
        )
    return current

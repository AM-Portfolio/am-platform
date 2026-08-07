#!/usr/bin/env python3
"""Build shared AM — Local/Dev/Preprod/Prod Postman environments."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULTS_PATH = ROOT / "am_environment.defaults.json"


def load_defaults() -> dict:
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


def resolve_aliases(values: dict[str, str], alias_map: dict[str, str]) -> dict[str, str]:
    resolved = dict(values)
    for alias, canonical in alias_map.items():
        if canonical in resolved:
            resolved[alias] = resolved[canonical]
        elif alias not in resolved:
            resolved[alias] = ""
    return resolved


def build_environment(profile_name: str) -> dict:
    cfg = load_defaults()
    profile = cfg["profiles"][profile_name]
    secret_keys = set(cfg.get("secret_keys", []))
    values_map: dict[str, str] = {}
    values_map.update(cfg.get("shared_defaults", {}))
    values_map.update(profile.get("values", {}))
    values_map = resolve_aliases(values_map, cfg.get("alias_map", {}))

    ordered_keys = cfg.get("ordered_keys", [])
    values: list[dict] = []
    seen: set[str] = set()

    for key in ordered_keys:
        if key not in values_map:
            continue
        values.append(
            {
                "key": key,
                "value": values_map[key],
                "type": "secret" if key in secret_keys else "default",
                "enabled": True,
            }
        )
        seen.add(key)

    for key in sorted(values_map):
        if key in seen:
            continue
        values.append(
            {
                "key": key,
                "value": values_map[key],
                "type": "secret" if key in secret_keys else "default",
                "enabled": True,
            }
        )

    return {
        "id": profile["id"],
        "name": profile["name"],
        "values": values,
        "_postman_variable_scope": "environment",
        "_postman_exported_at": "2026-08-06T00:00:00.000Z",
        "_postman_exported_using": "build_am_envs.py",
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    for name in ("local", "dev", "preprod", "prod"):
        path = ROOT / f"AM.{name}.postman_environment.json"
        write_json(path, build_environment(name))
        print(f"Wrote {path.name}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build unified AM Platform Postman collection + environments from per-service exports."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
PLATFORM = ROOT.parent
ENV_DEFAULTS_PATH = ROOT / "environment.defaults.json"

MODULES = (
    {
        "folder": "Identity",
        "slug": "identity",
        "base_var": "identity_base_url",
        "default_port": "8113",
        "collection": PLATFORM / "am-identity" / "postman" / "AM-Identity.postman_collection.json",
        "environment": PLATFORM / "am-identity" / "postman" / "AM-Identity.local.postman_environment.json",
    },
    {
        "folder": "Subscription",
        "slug": "subscription",
        "base_var": "subscription_base_url",
        "default_port": "8110",
        "collection": PLATFORM / "am-subscription" / "postman" / "AM-Subscription.postman_collection.json",
        "environment": PLATFORM / "am-subscription" / "postman" / "AM-Subscription.local.postman_environment.json",
    },
    {
        "folder": "Notification",
        "slug": "notification",
        "base_var": "notification_base_url",
        "default_port": "8111",
        "collection": PLATFORM / "am-notification" / "postman" / "AM-Notification.postman_collection.json",
        "environment": PLATFORM / "am-notification" / "postman" / "AM-Notification.local.postman_environment.json",
    },
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def js_to_exec(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def rewrite_base_url(obj, base_var: str):
    """Replace {{base_url}} with module-specific base URL variable."""
    replacement = f"{{{{{base_var}}}}}"
    if isinstance(obj, str):
        return obj.replace("{{base_url}}", replacement)
    if isinstance(obj, dict):
        for key, value in obj.items():
            obj[key] = rewrite_base_url(value, base_var)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            obj[index] = rewrite_base_url(item, base_var)
    return obj


def load_env_config() -> dict:
    return load_json(ENV_DEFAULTS_PATH)


def merge_module_env_keys() -> dict[str, dict]:
    """Seed from per-module env files (types/enabled), then apply platform defaults."""
    merged: dict[str, dict] = {}
    for module in MODULES:
        env = load_json(module["environment"])
        for entry in env.get("values", []):
            key = entry["key"]
            if key not in merged:
                merged[key] = entry
    return merged


def build_environment(profile_name: str) -> dict:
    cfg = load_env_config()
    profile = cfg["profiles"][profile_name]
    merged = merge_module_env_keys()
    secret_keys = set(cfg.get("secret_keys", []))
    values_map: dict[str, str] = {}
    values_map.update(cfg.get("shared_defaults", {}))
    values_map.update(profile.get("values", {}))

    for module in MODULES:
        port = module["default_port"]
        base_key = f"{module['slug']}_base_url"
        if profile_name == "local" and base_key not in profile.get("values", {}):
            values_map[base_key] = f"http://localhost:{port}"

    ordered_keys = cfg.get("ordered_keys", [])
    values: list[dict] = []
    seen: set[str] = set()

    for key in ordered_keys:
        if key not in values_map:
            continue
        entry = merged.get(key, {})
        values.append(
            {
                "key": key,
                "value": values_map[key],
                "type": "secret" if key in secret_keys else entry.get("type", "default"),
                "enabled": entry.get("enabled", True),
            }
        )
        seen.add(key)

    for key in sorted(values_map):
        if key in seen:
            continue
        entry = merged.get(key, {})
        values.append(
            {
                "key": key,
                "value": values_map[key],
                "type": "secret" if key in secret_keys else entry.get("type", "default"),
                "enabled": entry.get("enabled", True),
            }
        )

    return {
        "id": profile["id"],
        "name": profile["name"],
        "values": values,
        "_postman_variable_scope": "environment",
        "_postman_exported_at": "2026-05-30T00:00:00.000Z",
        "_postman_exported_using": "build_platform_postman.py",
    }


def collection_events() -> list[dict]:
    return [
        {
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": js_to_exec(SCRIPTS / "collection-prerequest.js"),
            },
        },
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": js_to_exec(SCRIPTS / "collection-test.js"),
            },
        },
    ]


def build_collection() -> dict:
    top_items = []
    all_variables: dict[str, str] = {}

    for module in MODULES:
        source = load_json(module["collection"])
        items = deepcopy(source.get("item", []))
        rewrite_base_url(items, module["base_var"])
        top_items.append(
            {
                "name": module["folder"],
                "description": source.get("info", {}).get("description", ""),
                "item": items,
            }
        )
        for var in source.get("variable", []):
            key = var["key"]
            if key == "base_url":
                all_variables[module["base_var"]] = f"http://localhost:{module['default_port']}"
            elif key not in all_variables:
                all_variables[key] = var.get("value", "")

    local_env = build_environment("local")
    for entry in local_env["values"]:
        if entry["key"].endswith("_base_url") or entry["key"] in all_variables:
            all_variables[entry["key"]] = entry["value"]

    collection_variables = [{"key": k, "value": v} for k, v in sorted(all_variables.items())]

    return {
        "info": {
            "_postman_id": "am-platform-collection-v1",
            "name": "AM Platform",
            "description": (
                "Unified Postman collection for **am-platform** thin-layer services.\n\n"
                "## Environments\n"
                "| File | Use when |\n"
                "|------|----------|\n"
                "| `AM-Platform.local.postman_environment.json` | `npm run platform:dev` (localhost) |\n"
                "| `AM-Platform.preprod.postman_environment.json` | Gateway at `am-dev.asrax.in/api` |\n\n"
                "## Auto-capture (collection scripts)\n"
                "**Pre-request:** fresh `idempotency_key` for meter/check POSTs; `X-Request-Id` header.\n\n"
                "**Post-response:** saves `access_token`, `refresh_token`, `service_access_token`, "
                "`user_sub`, `subscription_id`, `plan_code`, `notification_id`, Google SSO vars.\n\n"
                "## Modules\n"
                "| Folder | Service |\n"
                "|--------|--------|\n"
                "| Identity | am-identity |\n"
                "| Subscription | am-subscription |\n"
                "| Notification | am-notification |"
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "event": collection_events(),
        "variable": collection_variables,
        "item": top_items,
    }


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    collection_path = ROOT / "AM-Platform.postman_collection.json"
    local_path = ROOT / "AM-Platform.local.postman_environment.json"
    preprod_path = ROOT / "AM-Platform.preprod.postman_environment.json"

    write_json(collection_path, build_collection())
    write_json(local_path, build_environment("local"))
    write_json(preprod_path, build_environment("preprod"))

    print(f"Wrote {collection_path.name}")
    print(f"Wrote {local_path.name}")
    print(f"Wrote {preprod_path.name}")
    print(f"Scripts: {SCRIPTS.name}/collection-prerequest.js, collection-test.js")
    print(f"Modules: {', '.join(m['folder'] for m in MODULES)}")


if __name__ == "__main__":
    main()

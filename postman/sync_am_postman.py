#!/usr/bin/env python3
"""Sync AM shared envs and normalize Asrax Postman collections via Postman API."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
WORKSPACE_ID = "648a186b-f56c-4a95-b8ff-9a235cbde152"
API = "https://api.getpostman.com"
PREFER_DESC = "Prefer environment: AM — Local | Dev | Preprod | Prod"

COLLECTIONS: dict[str, dict[str, Any]] = {
    "1488e671-c13c-4cd7-a83b-912fdfc3389d": {
        "name": "Am-Market_data",
        "priority": "high",
        "host_to_var": {
            r"https?://am-dev\.asrax\.in/market": "{{market_base_url}}",
            r"https?://am-preprod\.asrax\.in/market": "{{market_base_url}}",
            r"https?://am\.asrax\.in/market": "{{market_base_url}}",
            r"https?://localhost:8084": "{{market_base_url}}",
            r"https?://localhost:8092": "{{market_base_url}}",
            r"https?://localhost:8000": "{{market_base_url}}",
            r"https?://127\.0\.0\.1:8084": "{{market_base_url}}",
        },
        "var_renames": {
            "market-baseurl": "market_base_url",
            "marketdataurl": "market_base_url",
            "jwt_token": "access_token",
            "bearerToken": "access_token",
        },
        "collection_base": ("market_base_url", "http://localhost:8084"),
    },
    "d7d43ddf-ce50-4da7-ad71-06a8ca20d579": {
        "name": "Am-Document_processor",
        "priority": "high",
        "host_to_var": {
            r"https?://localhost:8081": "{{doc_processor_base_url}}",
            r"https?://localhost:8070": "{{identity_base_url}}",
            r"https?://am-dev\.asrax\.in/doc/processor": "{{doc_processor_base_url}}",
            r"https?://am-preprod\.asrax\.in/doc/processor": "{{doc_processor_base_url}}",
            r"https?://am\.asrax\.in/doc/processor": "{{doc_processor_base_url}}",
        },
        "var_renames": {
            "document-baseurl": "doc_processor_base_url",
            "userid": "user_sub",
            "jwt_token": "access_token",
        },
        "collection_base": ("doc_processor_base_url", "http://localhost:8081"),
    },
    "c58e214a-ac25-4bb4-a4bd-33d3d64e0b8d": {
        "name": "AM Authentication System",
        "priority": "high",
        "host_to_var": {
            r"https?://localhost:8070": "{{identity_base_url}}",
            r"https?://localhost:8080": "{{gateway_base_url}}",
            r"https?://localhost:8092": "{{market_base_url}}",
            r"https?://am-dev\.asrax\.in/identity": "{{identity_base_url}}",
            r"https?://am\.asrax\.in/identity": "{{identity_base_url}}",
            r"https?://am-preprod\.asrax\.in/identity": "{{identity_base_url}}",
        },
        "var_renames": {
            "auth_url": "identity_base_url",
            "user_url": "identity_base_url",
            "jwt_token": "access_token",
            "bearerToken": "access_token",
        },
        "collection_base": ("identity_base_url", "http://localhost:8113"),
    },
    "529c9a20-70c5-44b8-893e-c7aa47a911fa": {
        "name": "AM Trade Metrics",
        "priority": "high",
        "host_to_var": {
            r"https?://localhost:8073": "{{trade_base_url}}",
            r"https?://am-dev\.asrax\.in/trade": "{{trade_base_url}}",
            r"https?://am-preprod\.asrax\.in/trade": "{{trade_base_url}}",
            r"https?://am\.asrax\.in/trade": "{{trade_base_url}}",
        },
        "var_renames": {
            "baseUrl": "trade_base_url",
            "baseurl": "trade_base_url",
            "trade-baseUrl": "trade_base_url",
            "jwt_token": "access_token",
            "authToken": "access_token",
            "bearerToken": "access_token",
        },
        "collection_base": ("trade_base_url", "http://localhost:8073"),
    },
    "5d059bfd-615e-4f4f-8ad2-0ba402dfc745": {
        "name": "AM Identity",
        "priority": "high",
        "host_to_var": {
            r"https?://localhost:8113": "{{identity_base_url}}",
            r"https?://am-dev\.asrax\.in/identity": "{{identity_base_url}}",
            r"https?://am-preprod\.asrax\.in/identity": "{{identity_base_url}}",
            r"https?://am\.asrax\.in/identity": "{{identity_base_url}}",
        },
        "var_renames": {
            "identityBase": "identity_base_url",
            "base_url": "identity_base_url",
            "bearerToken": "access_token",
            "jwt_token": "access_token",
        },
        "collection_base": ("identity_base_url", "http://localhost:8113"),
    },
    "edb33b13-f470-48ab-b1e6-5b463ede9752": {
        "name": "AM Portfolio",
        "priority": "high",
        "host_to_var": {
            r"https?://localhost:8085": "{{portfolio_base_url}}",
            r"https?://am-dev\.asrax\.in/portfolio": "{{portfolio_base_url}}",
            r"https?://am-preprod\.asrax\.in/portfolio": "{{portfolio_base_url}}",
            r"https?://am\.asrax\.in/portfolio": "{{portfolio_base_url}}",
        },
        "var_renames": {
            "baseUrl": "portfolio_base_url",
            "portfolioUrl": "portfolio_base_url",
            "commonDataBaseUrl": "portfolio_base_url",
            "jwt_token": "access_token",
            "bearerToken": "access_token",
        },
        "collection_base": ("portfolio_base_url", "http://localhost:8085"),
    },
    "326d18a1-d818-490f-b0b8-e7d2847c5a58": {
        "name": "AM MCP Gateway",
        "priority": "high",
        "host_to_var": {
            r"https?://localhost:8120": "{{mcp_gateway_base_url}}",
            r"https?://am-dev\.asrax\.in/mcp": "{{mcp_gateway_base_url}}",
            r"https?://am-preprod\.asrax\.in/mcp": "{{mcp_gateway_base_url}}",
            r"https?://am\.asrax\.in/mcp": "{{mcp_gateway_base_url}}",
        },
        "var_renames": {
            "mcp-gateway-base_url": "mcp_gateway_base_url",
            "base_url": "mcp_gateway_base_url",
            "jwt_token": "access_token",
            "bearerToken": "access_token",
        },
        "collection_base": ("mcp_gateway_base_url", "http://localhost:8120"),
    },
    "12889715-d5c1-40ff-a8fa-880532e106eb": {
        "name": "AM Parser",
        "priority": "high",
        "host_to_var": {
            r"https?://localhost:9000": "{{parser_base_url}}",
            r"https?://am-dev\.asrax\.in/parser": "{{parser_base_url}}",
            r"https?://am\.asrax\.in/parser": "{{parser_base_url}}",
        },
        "var_renames": {
            "parserurl": "parser_base_url",
            "base_url": "parser_base_url",
            "jwt_token": "access_token",
        },
        "collection_base": ("parser_base_url", "http://localhost:9000"),
    },
    "02e01746-a551-4302-ba5d-777c48a46076": {
        "name": "AM DB Agent",
        "priority": "medium",
        "var_renames": {"baseUrl": "db_agent_base_url", "base_url": "db_agent_base_url"},
        "collection_base": ("db_agent_base_url", "http://localhost:8140"),
    },
    "17a2e245-d5c0-429c-a7dd-8ce594ce8c49": {
        "name": "AM Tool Agent",
        "priority": "medium",
        "var_renames": {"baseUrl": "tools_base_url", "base_url": "tools_base_url"},
        "collection_base": ("tools_base_url", "http://localhost:8141"),
    },
    "6319a908-ae44-429d-bbf3-3838bcda4b2f": {
        "name": "am-fin-agent",
        "priority": "medium",
        "host_to_var": {
            r"https?://am-dev\.asrax\.in/ai": "{{ai_gateway_base_url}}",
            r"https?://am-preprod\.asrax\.in/ai": "{{ai_gateway_base_url}}",
            r"https?://am\.asrax\.in/ai": "{{ai_gateway_base_url}}",
        },
        "var_renames": {
            "ai_gateway_base": "ai_gateway_base_url",
            "bearerToken": "access_token",
            "jwt_token": "access_token",
        },
        "collection_base": ("ai_gateway_base_url", "https://am-dev.asrax.in/ai"),
    },
    "a4bde06d-593a-4333-b2fe-b30b1d3ea34b": {
        "name": "AM Analysis",
        "priority": "medium",
        "var_renames": {
            "analysis_url": "analysis_base_url",
            "base_url": "analysis_base_url",
            "jwt_token": "access_token",
        },
        "collection_base": ("analysis_base_url", "http://localhost:8080"),
    },
    "f7d940cd-68bb-4397-8bca-8c8574f8d388": {
        "name": "AM Gateway WS",
        "priority": "medium",
        "var_renames": {
            "gateway_url": "gateway_base_url",
            "base_url": "gateway_base_url",
            "jwt_token": "access_token",
        },
        "collection_base": ("gateway_base_url", "http://localhost:8080"),
    },
    "f8cf29f2-5cf9-4f2b-8857-042b2d98d372": {
        "name": "AM MCP Server",
        "priority": "medium",
        "var_renames": {
            "mcp_url": "mcp_base_url",
            "base_url": "mcp_base_url",
            "jwt_token": "access_token",
        },
        "collection_base": ("mcp_base_url", "https://am-dev.asrax.in/mcp"),
    },
    "f9b4f837-45bc-4090-8b0a-820587ae206d": {
        "name": "Cloudinary",
        "priority": "medium",
        "var_renames": {
            "cloudinary-baseurl": "cloudinary_base_url",
            "baseUrl": "cloudinary_base_url",
        },
        "collection_base": ("cloudinary_base_url", "http://localhost:8082"),
    },
    "ff80122a-a773-46da-b8b4-f0f1323a33e8": {
        "name": "qa-agent-local",
        "priority": "medium",
        "host_to_var": {
            r"https?://127\.0\.0\.1:8150": "{{qa_base_url}}",
            r"https?://localhost:8150": "{{qa_base_url}}",
        },
        "var_renames": {"baseUrl": "qa_base_url", "token": "access_token"},
        "collection_base": ("qa_base_url", "http://127.0.0.1:8150"),
    },
    "f7244466-feb6-448e-a69a-2d976758a5f3": {
        "name": "AM Platform",
        "priority": "low",
        "var_renames": {},
        "touch_description_only": True,
    },
    "0bff0007-02bf-4c94-9a0e-3dbf219d7aac": {
        "name": "AM Notification",
        "priority": "low",
        "var_renames": {},
        "touch_description_only": True,
    },
    "cb6386bf-336b-4f6d-8bfc-f5cffca270ce": {
        "name": "AM Subscription",
        "priority": "low",
        "var_renames": {},
        "touch_description_only": True,
    },
}


def load_api_key() -> str:
    key = os.environ.get("POSTMAN_API_KEY") or os.environ.get("POSTMAN_API_TOKEN")
    if key:
        return key.strip()
    cred = Path.home() / ".am" / "credentials.env"
    if cred.exists():
        for line in cred.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() in {"POSTMAN_API_KEY", "POSTMAN_API_TOKEN"}:
                return v.strip().strip('"').strip("'")
    raise SystemExit("POSTMAN_API_KEY not found in env or ~/.am/credentials.env")


def api_request(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "X-Api-Key": load_api_key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> {exc.code}: {detail}") from exc


def deep_replace_strings(obj: Any, replacer) -> Any:
    if isinstance(obj, str):
        return replacer(obj)
    if isinstance(obj, list):
        return [deep_replace_strings(x, replacer) for x in obj]
    if isinstance(obj, dict):
        return {k: deep_replace_strings(v, replacer) for k, v in obj.items()}
    return obj


def make_replacer(cfg: dict[str, Any]):
    host_rules = [
        (re.compile(pat, re.IGNORECASE), replacement)
        for pat, replacement in cfg.get("host_to_var", {}).items()
    ]
    renames = cfg.get("var_renames", {})

    def replace_vars(text: str) -> str:
        for old, new in renames.items():
            text = text.replace(f"{{{{{old}}}}}", f"{{{{{new}}}}}")
        return text

    def replacer(text: str) -> str:
        out = text
        for pattern, replacement in host_rules:
            out = pattern.sub(replacement, out)
        out = replace_vars(out)
        return out

    return replacer


def ensure_description(info: dict) -> None:
    desc = info.get("description") or ""
    if PREFER_DESC not in desc:
        info["description"] = (desc + ("\n\n" if desc else "") + PREFER_DESC).strip()


def upsert_collection_vars(collection: dict, cfg: dict[str, Any]) -> None:
    variables = collection.get("variable") or []
    by_key = {v.get("key"): v for v in variables if isinstance(v, dict) and v.get("key")}
    for old, new in cfg.get("var_renames", {}).items():
        if old in by_key and new not in by_key:
            entry = dict(by_key[old])
            entry["key"] = new
            by_key[new] = entry
        if old in by_key and old != new:
            del by_key[old]
    base = cfg.get("collection_base")
    if base:
        key, default = base
        if key not in by_key:
            by_key[key] = {"key": key, "value": default}
        if "access_token" not in by_key:
            by_key["access_token"] = {"key": "access_token", "value": ""}
    collection["variable"] = list(by_key.values())


def normalize_collection(uid: str, cfg: dict[str, Any], dry_run: bool) -> None:
    owner_uid = f"3526384-{uid}" if not uid.startswith("3526384-") else uid
    raw_uid = uid if "-" in uid and not uid.startswith("3526384") else uid.replace("3526384-", "", 1)
    full_uid = f"3526384-{raw_uid}"
    print(f"GET collection {cfg['name']} ({full_uid})")
    payload = api_request("GET", f"/collections/{full_uid}")
    collection = payload.get("collection")
    if not collection:
        raise RuntimeError(f"No collection payload for {full_uid}")

    ensure_description(collection.setdefault("info", {}))
    if not cfg.get("touch_description_only"):
        collection = deep_replace_strings(collection, make_replacer(cfg))
        upsert_collection_vars(collection, cfg)

    if dry_run:
        print(f"  dry-run: would PUT {cfg['name']}")
        return

    # Keep IDs so items are updated in place
    api_request("PUT", f"/collections/{full_uid}", {"collection": collection})
    print(f"  updated {cfg['name']}")


def load_env_files() -> list[dict]:
    envs = []
    for name in ("local", "dev", "preprod", "prod"):
        path = ROOT / f"AM.{name}.postman_environment.json"
        envs.append(json.loads(path.read_text(encoding="utf-8")))
    return envs


def sync_environments(dry_run: bool) -> None:
    existing = api_request("GET", f"/environments?workspace={WORKSPACE_ID}").get("environments", [])
    by_name = {e["name"]: e for e in existing}
    for env in load_env_files():
        name = env["name"]
        values = [
            {
                "key": v["key"],
                "value": v.get("value", ""),
                "type": v.get("type", "default") if v.get("type") in {"default", "secret"} else "default",
                "enabled": v.get("enabled", True),
            }
            for v in env.get("values", [])
        ]
        body = {"environment": {"name": name, "values": values}}
        if name in by_name:
            env_id = by_name[name]["uid"]
            print(f"PUT environment {name} ({env_id})")
            if not dry_run:
                api_request("PUT", f"/environments/{env_id}", body)
        else:
            print(f"POST environment {name}")
            if not dry_run:
                api_request(
                    "POST",
                    f"/environments?workspace={quote(WORKSPACE_ID)}",
                    body,
                )


def main() -> None:
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    only_envs = "--envs-only" in args
    only_collections = "--collections-only" in args
    priority_filter = None
    if "--high" in args:
        priority_filter = "high"
    elif "--medium" in args:
        priority_filter = "medium"

    if not only_collections:
        sync_environments(dry_run)

    if not only_envs:
        for uid, cfg in COLLECTIONS.items():
            if priority_filter and cfg.get("priority") != priority_filter:
                continue
            normalize_collection(uid, cfg, dry_run)


if __name__ == "__main__":
    main()

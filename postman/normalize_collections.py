#!/usr/bin/env python3
"""Normalize Asrax collections via patchCollection + per-request updates."""
from __future__ import annotations

import json
import re
import sys
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sync_am_postman import (
    API,
    COLLECTIONS,
    PREFER_DESC,
    load_api_key,
    make_replacer,
)

OWNER = "3526384"


def api(method: str, path: str, body: dict | None = None) -> dict:
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


def walk_requests(items: list, folder: str = "") -> list[dict]:
    found = []
    for item in items or []:
        name = item.get("name", "")
        path = f"{folder}/{name}" if folder else name
        if "request" in item:
            found.append({"path": path, "item": item})
        if "item" in item:
            found.extend(walk_requests(item["item"], path))
    return found


def raw_url(request: dict) -> str:
    url = request.get("url")
    if isinstance(url, str):
        return url
    if isinstance(url, dict):
        return url.get("raw") or ""
    return ""


def auth_or_headers_need_update(request: dict, replacer) -> bool:
    blob = json.dumps(request)
    return replacer(blob) != blob


def update_request(collection_id: str, request_id: str, request: dict, name: str) -> None:
    # Postman update request endpoint expects flattened-ish body
    url = raw_url(request)
    method = request.get("method", "GET")
    headers = []
    for h in request.get("header") or []:
        if isinstance(h, dict) and h.get("key"):
            headers.append(
                {
                    "key": h["key"],
                    "value": h.get("value", ""),
                    "description": h.get("description") or "",
                }
            )
    body: dict[str, Any] = {
        "name": name,
        "method": method,
        "url": url,
        "headerData": headers,
    }
    # include auth if present
    if request.get("auth"):
        body["auth"] = request["auth"]
    api("PUT", f"/collections/{collection_id}/requests/{request_id}", body)


def patch_collection_meta(full_uid: str, collection: dict, cfg: dict, dry_run: bool) -> None:
    info = collection.get("info") or {}
    desc = info.get("description") or ""
    if PREFER_DESC not in desc:
        desc = (desc + ("\n\n" if desc else "") + PREFER_DESC).strip()

    variables = []
    by_key = {}
    for v in collection.get("variable") or []:
        if isinstance(v, dict) and v.get("key"):
            by_key[v["key"]] = v
    for old, new in cfg.get("var_renames", {}).items():
        if old in by_key and new not in by_key:
            entry = {"key": new, "value": by_key[old].get("value", "")}
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
    for k, v in by_key.items():
        variables.append({"key": k, "value": v.get("value", "")})

    patch_body = {
        "collection": {
            "info": {"description": desc},
            "variable": variables,
        }
    }
    print(f"  PATCH meta ({len(variables)} vars)")
    if dry_run:
        return
    api("PATCH", f"/collections/{full_uid}", patch_body)


def normalize(uid: str, cfg: dict, dry_run: bool) -> tuple[int, int]:
    full_uid = f"{OWNER}-{uid}"
    collection_id = uid
    print(f"Normalize {cfg['name']}")
    payload = api("GET", f"/collections/{full_uid}")
    collection = payload["collection"]
    patch_collection_meta(full_uid, collection, cfg, dry_run)

    if cfg.get("touch_description_only"):
        return 0, 0

    replacer = make_replacer(cfg)
    requests = walk_requests(collection.get("item") or [])
    updated = 0
    skipped = 0
    for entry in requests:
        item = entry["item"]
        req = item.get("request") or {}
        req_id = item.get("id")
        if not req_id:
            skipped += 1
            continue
        before = json.dumps(req, sort_keys=True)
        after_req = json.loads(replacer(json.dumps(req)))
        after = json.dumps(after_req, sort_keys=True)
        if before == after:
            skipped += 1
            continue

        print(f"  UPDATE {entry['path']}")
        if dry_run:
            updated += 1
            continue
        try:
            update_request(collection_id, req_id, after_req, item.get("name") or "request")
            updated += 1
            time.sleep(0.25)
        except Exception as exc:
            print(f"    FAIL {exc}")
            time.sleep(1.0)
            try:
                update_request(collection_id, req_id, after_req, item.get("name") or "request")
                updated += 1
            except Exception as exc2:
                print(f"    FAIL2 {exc2}")
                skipped += 1
    print(f"  done updated={updated} skipped={skipped}")
    return updated, skipped


def main() -> None:
    args = set(sys.argv[1:])
    dry_run = "--dry-run" in args
    priority = None
    if "--high" in args:
        priority = "high"
    elif "--medium" in args:
        priority = "medium"
    elif "--low" in args:
        priority = "low"

    totals = [0, 0]
    for uid, cfg in COLLECTIONS.items():
        if priority and cfg.get("priority") != priority:
            continue
        u, s = normalize(uid, cfg, dry_run)
        totals[0] += u
        totals[1] += s
    print(f"TOTAL updated={totals[0]} skipped={totals[1]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Sync AM-Platform Postman collection + prod environment to Postman cloud."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.getpostman.com"
ROOT = Path(__file__).resolve().parents[1]
COLLECTION_UID = "3526384-f7244466-feb6-448e-a69a-2d976758a5f3"
PROD_ENV_UID = "3526384-32f454dd-7860-48b9-b633-5cde0e4e598e"


def _req(method: str, path: str, key: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={
            "X-Api-Key": key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Postman API {method} {path} -> {exc.code}: {err[:1200]}") from exc


def main() -> int:
    key = (os.getenv("POSTMAN_API_KEY") or "").strip()
    if not key:
        print("Set POSTMAN_API_KEY", file=sys.stderr)
        return 2

    collection_path = ROOT / "AM-Platform.postman_collection.json"
    env_path = ROOT / "AM-Platform.prod.postman_environment.json"
    collection = json.loads(collection_path.read_text(encoding="utf-8"))
    env_file = json.loads(env_path.read_text(encoding="utf-8"))

    _req("PUT", f"/collections/{COLLECTION_UID}", key, {"collection": collection})
    print(f"updated collection uid={COLLECTION_UID}")

    _req("PUT", f"/environments/{PROD_ENV_UID}", key, {"environment": env_file})
    print(f"updated environment uid={PROD_ENV_UID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

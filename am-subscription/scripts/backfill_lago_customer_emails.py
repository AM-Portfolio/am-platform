"""One-shot: set Lago customer.email from Keycloak for am-user-{uuid} rows."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

import httpx

# Optional: path to a JSON map {external_id: email} written by the laptop agent.
MAP_PATH = os.environ.get("EMAIL_MAP_PATH", "/tmp/lago_email_map.json")


async def list_missing(client: httpx.AsyncClient, base: str, headers: dict[str, str]) -> list[str]:
    missing: list[str] = []
    page = 1
    while True:
        r = await client.get(
            f"{base}/api/v1/customers",
            headers=headers,
            params={"page": page, "per_page": 100},
        )
        r.raise_for_status()
        data = r.json()
        customers = data.get("customers") or []
        if not customers:
            break
        for c in customers:
            if not (c.get("email") or "").strip():
                missing.append(str(c.get("external_id") or ""))
        meta = data.get("meta") or {}
        total_pages = int(meta.get("total_pages") or page)
        if page >= total_pages:
            break
        page += 1
    return [m for m in missing if m]


async def upsert_email(
    client: httpx.AsyncClient,
    base: str,
    headers: dict[str, str],
    external_id: str,
    email: str,
) -> int:
    body = {
        "customer": {
            "external_id": external_id,
            "name": email,
            "email": email,
        }
    }
    r = await client.post(f"{base}/api/v1/customers", headers=headers, json=body)
    return r.status_code


async def main() -> int:
    base = (os.environ.get("LAGO_API_URL") or "").rstrip("/")
    key = os.environ.get("LAGO_ORG_API_KEY") or ""
    if not base or not key:
        print("ERROR: LAGO_API_URL / LAGO_ORG_API_KEY not set", file=sys.stderr)
        return 2

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    email_map: dict[str, str] = {}
    if os.path.isfile(MAP_PATH):
        import json

        email_map = json.loads(open(MAP_PATH, encoding="utf-8").read())

    async with httpx.AsyncClient(timeout=60.0) as client:
        missing = await list_missing(client, base, headers)
        print(f"missing_count={len(missing)}")
        if not email_map:
            for ext in missing:
                print(ext)
            print("NO_MAP: wrote external ids only; provide EMAIL_MAP_PATH to apply")
            return 0

        updated = 0
        skipped = 0
        failed = 0
        for ext in missing:
            email = (email_map.get(ext) or "").strip()
            if not email:
                skipped += 1
                continue
            status = await upsert_email(client, base, headers, ext, email)
            if status in (200, 201):
                updated += 1
            else:
                failed += 1
                print(f"fail status={status} id={ext}")
        print(f"updated={updated} skipped={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

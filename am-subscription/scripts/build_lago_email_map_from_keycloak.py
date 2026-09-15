"""Build am-user-{id} -> email map from Keycloak (run in identity pod)."""

from __future__ import annotations

import json
import os
import sys

import httpx

REALM = os.environ.get("KEYCLOAK_REALM", "am-realm")
BASE = (os.environ.get("KEYCLOAK_URL") or "").rstrip("/")
USER = os.environ.get("KEYCLOAK_ADMIN_USER") or ""
PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD") or ""
OUT = os.environ.get("OUT_PATH", "/tmp/lago_email_map.json")


def main() -> int:
    if not BASE or not USER or not PASSWORD:
        print("ERROR: Keycloak admin env missing", file=sys.stderr)
        return 2

    with httpx.Client(timeout=60.0, verify=False) as client:
        token_resp = client.post(
            f"{BASE}/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": USER,
                "password": PASSWORD,
            },
        )
        token_resp.raise_for_status()
        token = token_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        mapping: dict[str, str] = {}
        first = 0
        page = 100
        while True:
            r = client.get(
                f"{BASE}/admin/realms/{REALM}/users",
                headers=headers,
                params={"first": first, "max": page},
            )
            r.raise_for_status()
            users = r.json()
            if not users:
                break
            for u in users:
                uid = u.get("id")
                email = (u.get("email") or u.get("username") or "").strip()
                if uid and email and "@" in email:
                    mapping[f"am-user-{uid}"] = email
            if len(users) < page:
                break
            first += page

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(mapping, f)
    print(f"mapped={len(mapping)} out={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

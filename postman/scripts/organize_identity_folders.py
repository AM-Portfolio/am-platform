#!/usr/bin/env python3
"""Nest Identity folders and drop numeric prefixes on sibling modules."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = ROOT / "am-identity" / "postman" / "AM-Identity.postman_collection.json"
SUBSCRIPTION = ROOT / "am-subscription" / "postman" / "AM-Subscription.postman_collection.json"
NOTIFICATION = ROOT / "am-notification" / "postman" / "AM-Notification.postman_collection.json"

IDENTITY_DESCRIPTION = """\
Source collection for **am-identity**. Do **not** import this file into Postman.

Use **AM Platform** (`postman/AM-Platform.postman_collection.json`). This JSON is the Identity folder source for `python postman/build_platform_postman.py`.

## Auth
Identity → **Auth** → **Login & Session**. Run one Login (Web / Android / iOS). Each sets `login_platform` and `oauth_client_id`. Then **Refresh → Last login**.

Working OTP is **Auth → Web OTP** (`/auth/web/otp/send` + `/verify`). `POST /auth/login/otp` is a 501 stub under **Auth → Deprecated**.

## QR without a phone
Collection Runner on **Flows → QR login (no phone)**: Start → Login (Android fake phone) → Approve → Poll. TTL ~120s.

If the localhost:9000 QR tab is already open, skip Start and reuse that tab's `device_link_id` (same `code_verifier`).

## Folders
| Folder | Purpose |
|--------|---------|
| Health | Liveness |
| Auth | Registration, email/password, login, Google, web OTP, step-up |
| Flows | Collection Runner (QR, web OTP) |
| Device Link | Individual QR APIs |
| Users | Bearer profile/settings |
| BFF Session | Cookie session |
| Security and Sessions | Events + sessions |
| Internal | Service-account only |
| Keycloak Helpers | Direct token calls |
"""


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def by_name(items: list[dict]) -> dict[str, dict]:
    return {item["name"]: item for item in items}


def rename(item: dict, name: str, description: str | None = None) -> dict:
    out = deepcopy(item)
    out["name"] = name
    if description is not None:
        out["description"] = description
    return out


def folder(name: str, description: str, items: list[dict]) -> dict:
    return {"name": name, "description": description, "item": items}


def split_named(items: list[dict], names: list[str]) -> tuple[list[dict], list[dict]]:
    wanted = set(names)
    picked: list[dict] = []
    rest: list[dict] = []
    for item in items:
        if item["name"] in wanted:
            picked.append(item)
        else:
            rest.append(item)
    order = {name: index for index, name in enumerate(names)}
    picked.sort(key=lambda item: order[item["name"]])
    return picked, rest


def organize_identity(col: dict) -> dict:
    src = by_name(col["item"])
    login = deepcopy(src["02 Auth — Login & Session"])
    login_items = login["item"]
    logins, rest = split_named(
        login_items,
        ["Login (Web)", "Login (Android)", "Login (iOS)"],
    )
    refreshes, rest = split_named(
        rest,
        ["Refresh (last login)", "Refresh (Web)", "Refresh (Android)", "Refresh (iOS)"],
    )
    logout, leftover = split_named(rest, ["Logout"])
    if leftover:
        raise SystemExit(f"unexpected login folder leftovers: {[i['name'] for i in leftover]}")

    login["name"] = "Login & Session"
    login["description"] = (
        "Password login is platform-specific. Run one Login, then Refresh → Last login "
        "(uses `oauth_client_id` from the login you just ran)."
    )
    login["item"] = [
        folder("Login", "Web 7d TTL (`am-web-client`). Android/iOS 15d TTL.", logins),
        folder("Refresh", "Last login follows `oauth_client_id`. Platform folders pin the client.", refreshes),
        *logout,
    ]

    security = deepcopy(src["09 Security and Sessions"])
    events, rest = split_named(security["item"], ["List Security Events", "Ack Security Event"])
    sessions, leftover = split_named(
        rest,
        ["List Login Sessions", "Revoke Login Session", "Revoke All Login Sessions"],
    )
    if leftover:
        raise SystemExit(f"unexpected security leftovers: {[i['name'] for i in leftover]}")
    security["name"] = "Security and Sessions"
    security["item"] = [
        folder("Events", "Security banner events. Ack after list.", events),
        folder("Sessions", "Active sessions. Revoke one or all (logout everywhere).", sessions),
    ]

    col["info"]["name"] = "AM Identity (source — do not import)"
    col["info"]["description"] = IDENTITY_DESCRIPTION
    col["item"] = [
        rename(src["00 Health"], "Health", "Liveness."),
        folder(
            "Auth",
            "Sign up, password login, Google, web OTP, step-up. Deprecated holds the 501 `/auth/login/otp` stub.",
            [
                rename(src["01 Auth — Registration"], "Registration"),
                rename(
                    src["01b Auth — Email verify and password"],
                    "Email verify and password",
                ),
                login,
                rename(src["03 Auth — Google SSO"], "Google SSO"),
                rename(
                    src["07 Auth — Web OTP"],
                    "Web OTP",
                    "Working web OTP (`/auth/web/otp/send` + `/verify`). Browser User-Agent required.",
                ),
                rename(src["10 Step-Up Auth"], "Step-up"),
                rename(
                    src["98 Deprecated"],
                    "Deprecated",
                    "501 stub. Do not use. Real OTP is Auth → Web OTP.",
                ),
            ],
        ),
        folder(
            "Flows (run in order)",
            "Collection Runner folders. Run top to bottom. QR TTL is ~120s; approve immediately after start.",
            [
                rename(
                    src["06b QR Login Flow (Runner Order)"],
                    "QR login (no phone)",
                    "API-only QR: Start → Android login (fake phone Bearer) → Approve → Poll → BFF Me. "
                    "If the browser QR tab is already open, skip Start and reuse that tab's device_link_id.",
                ),
                rename(
                    src["07b Web OTP Flow (Runner Order)"],
                    "Web OTP (email)",
                    "Send captures `otp_session_id`. Paste the email code into `web_otp_code`, then Verify.",
                ),
            ],
        ),
        rename(
            src["06 Auth — Device Link"],
            "Device Link",
            "Individual QR APIs. Prefer Flows → QR login (no phone) for a full run.",
        ),
        rename(src["04 Users (Bearer Required)"], "Users", "Bearer required. Login first."),
        rename(src["08 BFF Session"], "BFF Session", "Cookie session after web/QR login."),
        security,
        rename(
            src["05 Internal (Service Token Required)"],
            "Internal",
            "Service-account token required (Keycloak Helpers → Client Credentials).",
        ),
        rename(
            src["99 Keycloak Helpers (Setup / Debug)"],
            "Keycloak Helpers",
            "Direct Keycloak calls for setup and debug. Not the app login path.",
        ),
    ]
    return col


def rename_prefixes(col: dict, mapping: dict[str, tuple[str, str]]) -> dict:
    items = []
    for item in col["item"]:
        if item["name"] in mapping:
            name, description = mapping[item["name"]]
            items.append(rename(item, name, description))
        else:
            items.append(item)
    col["item"] = items
    return col


def main() -> None:
    identity = organize_identity(load(IDENTITY))
    dump(IDENTITY, identity)

    subscription = rename_prefixes(
        load(SUBSCRIPTION),
        {
            "00 Health": ("Health", "Liveness."),
            "01 Plans": ("Plans", "Public plan catalog."),
            "02 Subscriptions (Bearer Required)": (
                "Subscriptions",
                "Bearer required. Identity login first.",
            ),
            "03 Internal (Service Token Required)": (
                "Internal",
                "Service-account token required.",
            ),
            "04 Webhooks": ("Webhooks", "Provider callbacks."),
            "99 Keycloak Helpers (Setup / Debug)": (
                "Keycloak Helpers",
                "Direct token calls for setup and debug.",
            ),
        },
    )
    dump(SUBSCRIPTION, subscription)

    notification = rename_prefixes(
        load(NOTIFICATION),
        {
            "00 Health": ("Health", "Liveness and readiness."),
            "01 Inbox": ("Inbox", "Bearer required."),
            "02 Preferences": ("Preferences", "Bearer required."),
            "03 Internal": ("Internal", "Service-account token required."),
            "99 Keycloak Helpers": ("Keycloak Helpers", "Direct token calls for setup and debug."),
        },
    )
    dump(NOTIFICATION, notification)

    print(f"updated {IDENTITY.relative_to(ROOT)}")
    print(f"updated {SUBSCRIPTION.relative_to(ROOT)}")
    print(f"updated {NOTIFICATION.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Rewrite AM-Identity Postman login/OTP/email folders. Run once from repo."""
from __future__ import annotations

import json
from pathlib import Path

COLLECTION = (
    Path(__file__).resolve().parents[2]
    / "am-identity"
    / "postman"
    / "AM-Identity.postman_collection.json"
)

JSON_HEADER = [{"key": "Content-Type", "value": "application/json"}]
WEB_UA = [
    {
        "key": "User-Agent",
        "value": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
    },
    {"key": "Content-Type", "value": "application/json"},
]

CAPTURE_SESSION = [
    "if (pm.response.code >= 200 && pm.response.code < 300) {",
    "  try {",
    "    const body = pm.response.json();",
    "    if (body.device_link_id) {",
    "      pm.environment.set('device_link_id', body.device_link_id);",
    "      pm.collectionVariables.set('device_link_id', body.device_link_id);",
    "    }",
    "    if (body.confirmation_code) {",
    "      pm.environment.set('confirmation_code', body.confirmation_code);",
    "      pm.collectionVariables.set('confirmation_code', body.confirmation_code);",
    "    }",
    "    if (body.otp_session_id) {",
    "      pm.environment.set('otp_session_id', body.otp_session_id);",
    "      pm.collectionVariables.set('otp_session_id', body.otp_session_id);",
    "    }",
    "    if (body.tokens && body.tokens.access_token) {",
    "      pm.environment.set('access_token', body.tokens.access_token);",
    "      pm.collectionVariables.set('access_token', body.tokens.access_token);",
    "    }",
    "    if (body.tokens && body.tokens.refresh_token) {",
    "      pm.environment.set('refresh_token', body.tokens.refresh_token);",
    "      pm.collectionVariables.set('refresh_token', body.tokens.refresh_token);",
    "    }",
    "    const cookie = pm.cookies.get('am_session');",
    "    if (cookie) pm.environment.set('am_session', cookie);",
    "  } catch (e) {}",
    "}",
]

PKCE_PREREQUEST = [
    "const verifier = pm.variables.replaceIn('{{$guid}}') + pm.variables.replaceIn('{{$guid}}');",
    "const hash = CryptoJS.SHA256(verifier).toString(CryptoJS.enc.Base64)",
    "  .replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');",
    "pm.environment.set('code_verifier', verifier);",
    "pm.collectionVariables.set('code_verifier', verifier);",
    "pm.environment.set('code_challenge', hash);",
    "pm.collectionVariables.set('code_challenge', hash);",
]

BEARER = {
    "type": "bearer",
    "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
}

DESCRIPTION = """Source collection for **am-identity**. Do **not** import this file into Postman.

Use the generated **AM Platform** collection (`postman/AM-Platform.postman_collection.json`) instead. This JSON is the Identity folder source for `python postman/build_platform_postman.py`.

## Login
Use **02 Auth — Login & Session** with a platform-specific request:
- Login (Web) → `platform: web` → refresh with `am-web-client`
- Login (Android) → `platform: android` → refresh with `am-android-client`
- Login (iOS) → `platform: ios` → refresh with `am-ios-client`

Each login sets `login_platform` and `oauth_client_id`. Then use **Refresh (last login)** or the matching Refresh request.

## OTP
Working OTP is **07 Auth — Web OTP** (`/auth/web/otp/send` + `/verify`). `POST /auth/login/otp` is a 501 stub (Deprecated folder).

## QR without a phone
Run **06b QR Login Flow (Runner Order)** in order: Start → Login (Android fake phone) → Approve → Poll.

## Folders
| Folder | Purpose |
|--------|----------|
| 00 Health | Liveness |
| 01 Auth — Registration | Sign up |
| 01b Auth — Email verify and password | Reset / verify / change password |
| 02 Auth — Login & Session | Web / Android / iOS password login |
| 03 Auth — Google SSO | URL + callback + id_token |
| 04 Users | Bearer profile/settings |
| 05 Internal | Service-account only |
| 06 Device Link | QR web login APIs |
| 06b QR Login Flow | Collection runner (no phone) |
| 07 Web OTP | Email OTP (web only) |
| 07b Web OTP Flow | Collection runner |
| 08 BFF | Cookie session |
| 09 Security and Sessions | Events + sessions |
| 10 Step-Up | Trading prep |
| 98 Deprecated | 501 `/auth/login/otp` |
| 99 Keycloak Helpers | Direct token calls |
"""


def json_item(
    name: str,
    method: str,
    url: str,
    *,
    body: str | None = None,
    headers: list | None = None,
    auth: dict | None = None,
    description: str = "",
    events: list | None = None,
) -> dict:
    request: dict = {
        "method": method,
        "header": headers if headers is not None else JSON_HEADER,
        "url": url,
        "description": description,
    }
    if auth:
        request["auth"] = auth
    if body is not None and method != "GET":
        request["body"] = {"mode": "raw", "raw": body}
    item: dict = {"name": name, "request": request, "response": []}
    if events:
        item["event"] = events
    return item


def login_event(platform: str, client_id: str) -> list[dict]:
    return [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "if (pm.response.code >= 200 && pm.response.code < 300) {",
                    f"  pm.environment.set('login_platform', '{platform}');",
                    f"  pm.collectionVariables.set('login_platform', '{platform}');",
                    f"  pm.environment.set('oauth_client_id', '{client_id}');",
                    f"  pm.collectionVariables.set('oauth_client_id', '{client_id}');",
                    "}",
                ],
            },
        }
    ]


def login_item(label: str, platform: str, client_id: str, ttl: str) -> dict:
    return json_item(
        f"Login ({label})",
        "POST",
        "{{base_url}}/auth/login",
        body=(
            '{\n'
            '  "username": "{{test_email}}",\n'
            '  "password": "{{test_password}}",\n'
            f'  "platform": "{platform}"\n'
            "}"
        ),
        description=(
            f"Password grant as {label}. Sets tokens plus `login_platform={platform}` "
            f"and `oauth_client_id={client_id}` ({ttl})."
        ),
        events=login_event(platform, client_id),
    )


def refresh_item(label: str, client_id: str) -> dict:
    return json_item(
        f"Refresh ({label})",
        "POST",
        "{{base_url}}/auth/refresh",
        body=(
            '{\n'
            '  "refresh_token": "{{refresh_token}}",\n'
            f'  "client_id": "{client_id}"\n'
            "}"
        ),
        description=f"Refresh using {client_id}. Run the matching Login first.",
    )


def folder_login() -> dict:
    return {
        "name": "02 Auth — Login & Session",
        "description": (
            "Password login is **platform-specific**. Run one Login, then Refresh "
            "(last login) or the matching Refresh. Logout uses the last `oauth_client_id`."
        ),
        "item": [
            login_item("Web", "web", "am-web-client", "7d TTL"),
            login_item("Android", "android", "am-android-client", "15d TTL"),
            login_item("iOS", "ios", "am-ios-client", "15d TTL"),
            json_item(
                "Refresh (last login)",
                "POST",
                "{{base_url}}/auth/refresh",
                body=(
                    '{\n'
                    '  "refresh_token": "{{refresh_token}}",\n'
                    '  "client_id": "{{oauth_client_id}}"\n'
                    "}"
                ),
                description="Uses `oauth_client_id` set by the last platform Login.",
            ),
            refresh_item("Web", "am-web-client"),
            refresh_item("Android", "am-android-client"),
            refresh_item("iOS", "am-ios-client"),
            json_item(
                "Logout",
                "POST",
                "{{base_url}}/auth/logout",
                body=(
                    '{\n'
                    '  "refresh_token": "{{refresh_token}}",\n'
                    '  "client_id": "{{oauth_client_id}}"\n'
                    "}"
                ),
                description="Revokes the refresh session for the last login client. Expect 204.",
            ),
        ],
    }


def folder_email() -> dict:
    return {
        "name": "01b Auth — Email verify and password",
        "description": (
            "Mailbox verify and password reset. Codes/tokens come from email "
            "(or identity logs). Confirm endpoints expect exactly one of `token` or `code`."
        ),
        "item": [
            json_item(
                "Resend Verify Email",
                "POST",
                "{{base_url}}/auth/verify-email/resend",
                body='{\n  "email": "{{test_email}}"\n}',
                description="Always 202. Sends branded verify-email if the user exists.",
            ),
            json_item(
                "Confirm Verify Email",
                "POST",
                "{{base_url}}/auth/verify-email/confirm",
                body='{\n  "code": "{{verify_email_code}}"\n}',
                description="Set `verify_email_code` from email. Can use `token` instead of `code`.",
            ),
            json_item(
                "Password Reset Request",
                "POST",
                "{{base_url}}/auth/password-reset",
                body='{\n  "email": "{{test_email}}"\n}',
                description="Always 202. Sends reset email if the user exists.",
            ),
            json_item(
                "Password Reset Confirm",
                "POST",
                "{{base_url}}/auth/password-reset/confirm",
                body=(
                    '{\n'
                    '  "code": "{{password_reset_code}}",\n'
                    '  "new_password": "{{test_password}}"\n'
                    "}"
                ),
                description="Set `password_reset_code` from email. Can use `token` instead of `code`.",
            ),
            json_item(
                "Change Password",
                "POST",
                "{{base_url}}/auth/change-password",
                body=(
                    '{\n'
                    '  "email": "{{test_email}}",\n'
                    '  "current_password": "{{test_password}}",\n'
                    '  "new_password": "{{test_password}}"\n'
                    "}"
                ),
                description="Authenticated by current password, not Bearer.",
            ),
        ],
    }


def folder_deprecated() -> dict:
    return {
        "name": "98 Deprecated",
        "description": "Do not use. Left for contract checks only.",
        "item": [
            json_item(
                "Login OTP (501 stub)",
                "POST",
                "{{base_url}}/auth/login/otp",
                body=(
                    '{\n'
                    '  "username": "{{test_email}}",\n'
                    '  "otp": "123456"\n'
                    "}"
                ),
                description=(
                    "Scaffolded Keycloak OTP. Always 501. Use **07 Auth — Web OTP** "
                    "(`/auth/web/otp/send` + `/verify`) instead."
                ),
            )
        ],
    }


def folder_qr_runner() -> dict:
    start = json_item(
        "1 Device Link Start",
        "POST",
        "{{base_url}}/auth/device-link/start",
        headers=WEB_UA,
        body=(
            '{\n'
            '  "client": "web",\n'
            '  "redirect_hint": "http://localhost:9000/login",\n'
            '  "code_challenge": "{{code_challenge}}",\n'
            '  "browser": "Chrome",\n'
            '  "os": "Windows"\n'
            "}"
        ),
        description=(
            "Creates the QR session (PKCE). Captures `device_link_id` and "
            "`confirmation_code`. Skip this step if you already started QR in the browser "
            "and pasted those values from Network."
        ),
        events=[
            {"listen": "prerequest", "script": {"type": "text/javascript", "exec": PKCE_PREREQUEST}},
            {"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_SESSION}},
        ],
    )
    login = login_item("Android fake phone", "android", "am-android-client", "15d TTL")
    login["name"] = "2 Login (Android — fake phone Bearer)"
    login["request"]["description"] = (
        "Password login as the phone. Saves `access_token` for Approve. No mobile app needed."
    )
    approve = json_item(
        "3 Device Link Approve",
        "POST",
        "{{base_url}}/auth/device-link/{{device_link_id}}/approve",
        auth=BEARER,
        body=(
            '{\n'
            '  "confirmation_code": "{{confirmation_code}}",\n'
            '  "device_name": "Postman fake phone",\n'
            '  "machine_label": "QR Flow Test"\n'
            "}"
        ),
        description="Mobile approve stand-in. Must run while the link is still pending (TTL ~120s).",
    )
    poll = json_item(
        "4 Device Link Poll Approved",
        "GET",
        "{{base_url}}/auth/device-link/{{device_link_id}}/status?code_verifier={{code_verifier}}",
        headers=[{"key": "X-Machine-Trust-Key", "value": "{{machine_trust_key}}"}],
        description="Same PKCE verifier as Start. Expect status approved and am_session cookie.",
        events=[{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_SESSION}}],
    )
    poll["request"].pop("header", None)
    poll["request"]["header"] = [{"key": "X-Machine-Trust-Key", "value": "{{machine_trust_key}}"}]
    bff = json_item(
        "5 BFF Me (Cookie Session)",
        "GET",
        "{{base_url}}/bff/me",
        headers=[{"key": "Cookie", "value": "am_session={{am_session}}"}],
        description="Uses am_session from poll Set-Cookie.",
    )
    return {
        "name": "06b QR Login Flow (Runner Order)",
        "description": (
            "No phone required. Collection Runner order:\n"
            "1 Start → 2 Login (Android fake phone) → 3 Approve → 4 Poll → 5 BFF Me.\n"
            "If the browser QR tab is already open, skip Start and set `device_link_id` + "
            "`confirmation_code` + `code_verifier` from that tab instead (verifier lives in "
            "the browser, so API-only Poll will not complete a browser-started QR)."
        ),
        "item": [start, login, approve, poll, bff],
    }


def folder_otp_runner() -> dict:
    send = json_item(
        "1 Web OTP Send (Email)",
        "POST",
        "{{base_url}}/auth/web/otp/send",
        headers=WEB_UA,
        body='{\n  "channel": "email",\n  "destination": "{{test_email}}"\n}',
        description="Captures `otp_session_id`. Copy the 6-digit code from email into `web_otp_code`.",
        events=[{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_SESSION}}],
    )
    verify = json_item(
        "2 Web OTP Verify",
        "POST",
        "{{base_url}}/auth/web/otp/verify",
        headers=WEB_UA,
        body=(
            '{\n'
            '  "otp_session_id": "{{otp_session_id}}",\n'
            '  "code": "{{web_otp_code}}"\n'
            "}"
        ),
        description="Set `web_otp_code` from the email, then run. Saves tokens / am_session cookie.",
        events=[{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_SESSION}}],
    )
    return {
        "name": "07b Web OTP Flow (Runner Order)",
        "description": (
            "Working web OTP (not `/auth/login/otp`). Pause after Send, set `web_otp_code` "
            "from email or identity logs, then Verify."
        ),
        "item": [send, verify],
    }


def ensure_variable(variables: list[dict], key: str, value: str = "") -> None:
    if any(item.get("key") == key for item in variables):
        return
    variables.append({"key": key, "value": value})


def main() -> None:
    data = json.loads(COLLECTION.read_text(encoding="utf-8"))
    data["info"]["description"] = DESCRIPTION
    data["info"]["name"] = "AM Identity (source — do not import)"

    variables = data.setdefault("variable", [])
    ensure_variable(variables, "login_platform", "web")
    ensure_variable(variables, "oauth_client_id", "am-web-client")
    ensure_variable(variables, "verify_email_code", "")
    ensure_variable(variables, "password_reset_code", "")

    items = data["item"]
    by_name = {item["name"]: i for i, item in enumerate(items)}

    items[by_name["02 Auth — Login & Session"]] = folder_login()
    items[by_name["06b QR Login Flow (Runner Order)"]] = folder_qr_runner()

    insert_at = by_name["01 Auth — Registration"] + 1
    items.insert(insert_at, folder_email())

    by_name = {item["name"]: i for i, item in enumerate(items)}
    otp_at = by_name["07 Auth — Web OTP"] + 1
    items.insert(otp_at, folder_otp_runner())

    by_name = {item["name"]: i for i, item in enumerate(items)}
    deprecated_at = by_name["99 Keycloak Helpers (Setup / Debug)"]
    items.insert(deprecated_at, folder_deprecated())

    COLLECTION.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {COLLECTION}")
    print("folders:", [item["name"] for item in data["item"]])


if __name__ == "__main__":
    main()

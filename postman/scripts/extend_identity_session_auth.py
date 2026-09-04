#!/usr/bin/env python3
"""Merge identity session auth Postman folders into AM-Identity collection."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = ROOT.parent / "am-identity" / "postman" / "AM-Identity.postman_collection.json"

PKCE_PREREQUEST = [
    "const verifier = pm.variables.replaceIn('{{$guid}}') + pm.variables.replaceIn('{{$guid}}');",
    "const hash = CryptoJS.SHA256(verifier).toString(CryptoJS.enc.Base64)",
    "  .replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');",
    "pm.environment.set('code_verifier', verifier);",
    "pm.collectionVariables.set('code_verifier', verifier);",
    "pm.environment.set('code_challenge', hash);",
    "pm.collectionVariables.set('code_challenge', hash);",
]

CAPTURE_DEVICE_LINK = [
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
    "    }",
    "    if (body.step_up_token) {",
    "      pm.environment.set('step_up_token', body.step_up_token);",
    "    }",
    "    const cookie = pm.cookies.get('am_session');",
    "    if (cookie) pm.environment.set('am_session', cookie);",
    "    if (Array.isArray(body) && body.length) {",
    "      if (body[0].session_id) pm.environment.set('login_session_id', body[0].session_id);",
    "      if (body[0].event_id) pm.environment.set('security_event_id', body[0].event_id);",
    "    }",
    "  } catch (e) {}",
    "}",
]

BEARER = {
    "type": "bearer",
    "bearer": [{"key": "token", "value": "{{access_token}}", "type": "string"}],
}

WEB_UA = [
    {"key": "User-Agent", "value": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
    {"key": "Content-Type", "value": "application/json"},
]

MOBILE_UA = [
    {"key": "User-Agent", "value": "okhttp/4.12.0"},
    {"key": "Content-Type", "value": "application/json"},
]


def json_request(method: str, url: str, body: str, *, headers: list | None = None, auth=None, description: str = ""):
    req: dict = {
        "method": method,
        "header": headers or [{"key": "Content-Type", "value": "application/json"}],
        "url": url,
        "description": description,
    }
    if auth:
        req["auth"] = auth
    if body and method != "GET":
        req["body"] = {"mode": "raw", "raw": body}
    return {"name": "", "request": req, "response": []}


def new_folders() -> list[dict]:
    return [
        {
            "name": "06 Auth — Device Link",
            "description": "QR web login backend. Run **Start** first (PKCE auto-generated).",
            "item": [
                {
                    "name": "Device Link Start",
                    "event": [
                        {"listen": "prerequest", "script": {"type": "text/javascript", "exec": PKCE_PREREQUEST}},
                        {"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}},
                    ],
                    "request": {
                        "method": "POST",
                        "header": WEB_UA,
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "client": "web",\n  "redirect_hint": "http://localhost:9000/login",\n  "code_challenge": "{{code_challenge}}",\n  "browser": "Chrome",\n  "os": "Windows"\n}',
                        },
                        "url": "{{base_url}}/auth/device-link/start",
                        "description": "Creates device link; saves device_link_id and confirmation_code.",
                    },
                    "response": [],
                },
                {
                    "name": "Device Link Status (Poll)",
                    "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}}],
                    "request": {
                        "method": "GET",
                        "header": [
                            {"key": "X-Machine-Trust-Key", "value": "{{machine_trust_key}}"},
                        ],
                        "url": "{{base_url}}/auth/device-link/{{device_link_id}}/status?code_verifier={{code_verifier}}",
                        "description": "Poll until approved; captures am_session cookie on success.",
                    },
                    "response": [],
                },
                {
                    "name": "Device Link Preview",
                    "request": {
                        "auth": BEARER,
                        "method": "GET",
                        "header": [],
                        "url": "{{base_url}}/auth/device-link/{{device_link_id}}/preview",
                        "description": "Mobile scanner preview (Bearer required).",
                    },
                    "response": [],
                },
                {
                    "name": "Device Link Approve",
                    "request": {
                        "auth": BEARER,
                        "method": "POST",
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "confirmation_code": "{{confirmation_code}}",\n  "machine_label": "Postman Test Laptop",\n  "device_name": "Chrome on Windows"\n}',
                        },
                        "url": "{{base_url}}/auth/device-link/{{device_link_id}}/approve",
                        "description": "Mobile approves QR login.",
                    },
                    "response": [],
                },
                {
                    "name": "Device Link Deny",
                    "request": {
                        "auth": BEARER,
                        "method": "POST",
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": {"mode": "raw", "raw": '{\n  "reason": "Not me"\n}'},
                        "url": "{{base_url}}/auth/device-link/{{device_link_id}}/deny",
                    },
                    "response": [],
                },
                {
                    "name": "Device Link Cancel",
                    "request": {
                        "method": "POST",
                        "header": [],
                        "url": "{{base_url}}/auth/device-link/{{device_link_id}}/cancel",
                    },
                    "response": [],
                },
            ],
        },
        {
            "name": "06b QR Login Flow (Runner Order)",
            "description": "Run in order: Login → Start → Approve → Poll → BFF Me",
            "item": [
                {
                    "name": "1 Login (for Approve Bearer)",
                    "request": {
                        "method": "POST",
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "username": "{{test_email}}",\n  "password": "{{test_password}}",\n  "platform": "android"\n}',
                        },
                        "url": "{{base_url}}/auth/login",
                    },
                    "response": [],
                },
                {
                    "name": "2 Device Link Start",
                    "event": [
                        {"listen": "prerequest", "script": {"type": "text/javascript", "exec": PKCE_PREREQUEST}},
                        {"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}},
                    ],
                    "request": {
                        "method": "POST",
                        "header": WEB_UA,
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "client": "web",\n  "redirect_hint": "http://localhost:9000/login",\n  "code_challenge": "{{code_challenge}}",\n  "browser": "Chrome",\n  "os": "Windows"\n}',
                        },
                        "url": "{{base_url}}/auth/device-link/start",
                    },
                    "response": [],
                },
                {
                    "name": "3 Device Link Approve",
                    "request": {
                        "auth": BEARER,
                        "method": "POST",
                        "header": [{"key": "Content-Type", "value": "application/json"}],
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "confirmation_code": "{{confirmation_code}}",\n  "machine_label": "QR Flow Test"\n}',
                        },
                        "url": "{{base_url}}/auth/device-link/{{device_link_id}}/approve",
                    },
                    "response": [],
                },
                {
                    "name": "4 Device Link Poll Approved",
                    "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}}],
                    "request": {
                        "method": "GET",
                        "header": [{"key": "X-Machine-Trust-Key", "value": "{{machine_trust_key}}"}],
                        "url": "{{base_url}}/auth/device-link/{{device_link_id}}/status?code_verifier={{code_verifier}}",
                    },
                    "response": [],
                },
                {
                    "name": "5 BFF Me (Cookie Session)",
                    "request": {
                        "method": "GET",
                        "header": [{"key": "Cookie", "value": "am_session={{am_session}}"}],
                        "url": "{{base_url}}/bff/me",
                        "description": "Uses am_session from poll Set-Cookie.",
                    },
                    "response": [],
                },
            ],
        },
        {
            "name": "07 Auth — Web OTP",
            "description": "Web-only OTP login. Requires browser User-Agent.",
            "item": [
                {
                    "name": "Web OTP Send (Email)",
                    "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}}],
                    "request": {
                        "method": "POST",
                        "header": WEB_UA,
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "channel": "email",\n  "destination": "{{test_email}}"\n}',
                        },
                        "url": "{{base_url}}/auth/web/otp/send",
                    },
                    "response": [],
                },
                {
                    "name": "Web OTP Verify",
                    "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}}],
                    "request": {
                        "method": "POST",
                        "header": WEB_UA,
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "otp_session_id": "{{otp_session_id}}",\n  "code": "{{web_otp_code}}"\n}',
                        },
                        "url": "{{base_url}}/auth/web/otp/verify",
                    },
                    "response": [],
                },
                {
                    "name": "Web OTP Send (Mobile UA — expect 403)",
                    "request": {
                        "method": "POST",
                        "header": MOBILE_UA,
                        "body": {
                            "mode": "raw",
                            "raw": '{\n  "channel": "email",\n  "destination": "{{test_email}}"\n}',
                        },
                        "url": "{{base_url}}/auth/web/otp/send",
                    },
                    "response": [],
                },
            ],
        },
        {
            "name": "08 BFF Session",
            "item": [
                {
                    "name": "BFF Me",
                    "request": {
                        "method": "GET",
                        "header": [{"key": "Cookie", "value": "am_session={{am_session}}"}],
                        "url": "{{base_url}}/bff/me",
                    },
                    "response": [],
                },
                {
                    "name": "BFF Audit Log",
                    "request": {"method": "GET", "header": [], "url": "{{base_url}}/bff/audit"},
                    "response": [],
                },
            ],
        },
        {
            "name": "09 Security and Sessions",
            "item": [
                {
                    "name": "List Security Events",
                    "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}}],
                    "request": {
                        "auth": BEARER,
                        "method": "GET",
                        "header": [],
                        "url": "{{base_url}}/users/me/security-events",
                    },
                    "response": [],
                },
                {
                    "name": "Ack Security Event",
                    "request": {
                        "auth": BEARER,
                        "method": "POST",
                        "header": [],
                        "url": "{{base_url}}/users/me/security-events/{{security_event_id}}/ack",
                    },
                    "response": [],
                },
                {
                    "name": "List Login Sessions",
                    "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}}],
                    "request": {
                        "auth": BEARER,
                        "method": "GET",
                        "header": [],
                        "url": "{{base_url}}/users/me/login-sessions",
                    },
                    "response": [],
                },
                {
                    "name": "Revoke Login Session",
                    "request": {
                        "auth": BEARER,
                        "method": "DELETE",
                        "header": [],
                        "url": "{{base_url}}/users/me/login-sessions/{{login_session_id}}",
                    },
                    "response": [],
                },
                {
                    "name": "Revoke All Login Sessions",
                    "request": {
                        "auth": BEARER,
                        "method": "DELETE",
                        "header": [],
                        "url": "{{base_url}}/users/me/login-sessions",
                    },
                    "response": [],
                },
            ],
        },
        {
            "name": "10 Step-Up Auth",
            "item": [
                {
                    "name": "Issue Step-Up Token",
                    "event": [{"listen": "test", "script": {"type": "text/javascript", "exec": CAPTURE_DEVICE_LINK}}],
                    "request": {
                        "auth": BEARER,
                        "method": "POST",
                        "header": [],
                        "url": "{{base_url}}/auth/step-up",
                    },
                    "response": [],
                },
            ],
        },
    ]


def merge() -> None:
    data = json.loads(COLLECTION.read_text(encoding="utf-8"))

    data["info"]["description"] += (
        "\n| 06 Device Link | QR web login |\n"
        "| 07 Web OTP | Email/SMS web login |\n"
        "| 08 BFF | Cookie session |\n"
        "| 09 Security | Events + sessions |\n"
        "| 10 Step-Up | Trading prep |"
    )

    extra_vars = [
        ("device_link_id", ""),
        ("code_verifier", ""),
        ("code_challenge", ""),
        ("confirmation_code", ""),
        ("am_session", ""),
        ("step_up_token", ""),
        ("login_session_id", ""),
        ("security_event_id", ""),
        ("machine_trust_key", "postman-test-machine-trust-key"),
        ("web_otp_code", ""),
        ("otp_session_id", ""),
    ]
    existing = {v["key"] for v in data.get("variable", [])}
    for key, value in extra_vars:
        if key not in existing:
            data.setdefault("variable", []).append({"key": key, "value": value})

    for item in data["item"]:
        if item["name"] == "02 Auth — Login & Session":
            for sub in item["item"]:
                if sub["name"] == "Login (Password)":
                    sub["request"]["body"]["raw"] = (
                        '{\n  "username": "{{test_email}}",\n  '
                        '"password": "{{test_password}}",\n  '
                        '"platform": "android"\n}'
                    )
                if sub["name"] == "Refresh Token":
                    sub["request"]["body"]["raw"] = (
                        '{\n  "refresh_token": "{{refresh_token}}",\n  '
                        '"client_id": "am-android-client"\n}'
                    )

    names = {item["name"] for item in data["item"]}
    insert_before = "99 Keycloak Helpers (Setup / Debug)"
    new_items = new_folders()
    filtered = [f for f in new_items if f["name"] not in names]
    if not filtered:
        print("Session auth folders already present; skipping insert.")
        return

    out: list[dict] = []
    for item in data["item"]:
        if item["name"] == insert_before:
            out.extend(filtered)
        out.append(item)
    if insert_before not in names:
        out.extend(filtered)
    data["item"] = out

    COLLECTION.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Updated {COLLECTION.name} with {len(filtered)} folder(s)")


if __name__ == "__main__":
    merge()

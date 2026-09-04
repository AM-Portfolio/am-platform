"""Rebuild Postman collection + browser-safe prod env; never print secrets."""

from __future__ import annotations

import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
import uuid

HOME = pathlib.Path.home()
CREDS = HOME / ".asrax" / "credentials.env"
ROOT = pathlib.Path(__file__).resolve().parents[1]
POSTMAN_DIR = ROOT / "postman"
WORKSPACE = "c1ed9ba4-e485-4377-8374-7685abf4247d"
COLLECTION_UID = "56761657-a9fa5747-49c7-487e-8091-da3262f5a944"
PORT_FORWARD_ENV_UID = "56761657-3f6f40c7-80f0-4a72-9b6d-344dfeb183c3"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def load_creds() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def http_json(method: str, url: str, headers: dict, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={**headers, "User-Agent": UA}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:400]}


def admin_token(creds: dict) -> tuple[str, str]:
    kc = (creds.get("KEYCLOAK_URL") or "https://auth.asrax.in/auth").rstrip("/")
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": creds["KEYCLOAK_ADMIN"],
            "password": creds["KEYCLOAK_ADMIN_PASSWORD"],
        }
    ).encode()
    code, body = http_json(
        "POST",
        f"{kc}/realms/master/protocol/openid-connect/token",
        {"Content-Type": "application/x-www-form-urlencoded"},
        None,
    )
    # http_json with form needs raw body — special-case
    req = urllib.request.Request(
        f"{kc}/realms/master/protocol/openid-connect/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        tok = json.loads(resp.read().decode())["access_token"]
    return kc, tok


def client_secret(kc: str, token: str, client_id: str) -> str:
    code, clients = http_json(
        "GET",
        f"{kc}/admin/realms/am-realm/clients?clientId={urllib.parse.quote(client_id)}&max=1",
        {"Authorization": f"Bearer {token}"},
    )
    if code != 200 or not isinstance(clients, list) or not clients:
        raise SystemExit(f"client {client_id} not found HTTP {code}")
    cid = clients[0]["id"]
    code, secret = http_json(
        "GET",
        f"{kc}/admin/realms/am-realm/clients/{cid}/client-secret",
        {"Authorization": f"Bearer {token}"},
    )
    if code != 200 or not isinstance(secret, dict) or not secret.get("value"):
        raise SystemExit(f"secret for {client_id} failed HTTP {code}")
    return secret["value"]


def reset_test_password(kc: str, token: str, email: str) -> str:
    q = urllib.parse.urlencode({"email": email, "exact": "true"})
    code, users = http_json(
        "GET",
        f"{kc}/admin/realms/am-realm/users?{q}",
        {"Authorization": f"Bearer {token}"},
    )
    if code != 200 or not isinstance(users, list) or not users:
        raise SystemExit(f"user {email} not found")
    uid = users[0]["id"]
    pw = "Tmp" + uuid.uuid4().hex[:12] + "9A"
    code, _ = http_json(
        "PUT",
        f"{kc}/admin/realms/am-realm/users/{uid}/reset-password",
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        {"type": "password", "value": pw, "temporary": False},
    )
    if code not in (200, 204):
        raise SystemExit(f"reset password HTTP {code}")
    return pw


def bearer_auth(token_var: str) -> dict:
    return {
        "type": "bearer",
        "bearer": [{"key": "token", "value": f"{{{{{token_var}}}}}", "type": "string"}],
    }


def req(name: str, method: str, url: str, **kwargs) -> dict:
    out: dict = {
        "name": name,
        "request": {
            "method": method,
            "header": kwargs.get("header", []),
            "url": url,
            "description": kwargs.get("description", ""),
        },
        "response": [],
    }
    if "auth" in kwargs:
        out["request"]["auth"] = kwargs["auth"]
    if "body" in kwargs:
        out["request"]["body"] = kwargs["body"]
    if "event" in kwargs:
        out["event"] = kwargs["event"]
    return out


def build_collection() -> dict:
    login_tests = [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "if (pm.response.code === 200) {",
                    "  const b = pm.response.json();",
                    "  if (b.access_token) {",
                    "    pm.environment.set('access_token', b.access_token);",
                    "    try {",
                    "      const payload = JSON.parse(atob(b.access_token.split('.')[1]));",
                    "      if (payload.sub) pm.environment.set('user_sub', payload.sub);",
                    "    } catch (e) {}",
                    "  }",
                    "}",
                ],
            },
        }
    ]
    svc_tests = [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "if (pm.response.code === 200) {",
                    "  const b = pm.response.json();",
                    "  if (b.access_token) pm.environment.set('service_access_token', b.access_token);",
                    "}",
                ],
            },
        }
    ]
    return {
        "info": {
            "name": "AM User Platform Service",
            "description": (
                "AI chat memory APIs for **am-user-platform** + gateway proxies.\n\n"
                "## Browser Postman (no desktop install)\n"
                "1. Top-right: select **AM User Platform — Prod Public (Browser)**\n"
                "2. Run **00 Auth** → Password Login, then Client Credentials (gateway)\n"
                "3. Run **02 User Sessions (public)** and **03 Gateway Sessions**\n\n"
                "**Browser cannot call localhost.** Health + Internal need laptop port-forward "
                "(`base_url=http://127.0.0.1:8115`) — use env **Prod Port-Forward** only on desktop "
                "or leave them to agent smoke scripts.\n\n"
                "| Folder | Works in browser? |\n|--------|-------------------|\n"
                "| 00 Auth | yes |\n| 01 Health / Internal | only with port-forward |\n"
                "| 02 User Sessions (public) | yes |\n| 03 Gateway Sessions | yes (what Flutter will call) |\n"
                "| 04 Feedback | yes |\n"
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "event": [
            {
                "listen": "prerequest",
                "script": {
                    "type": "text/javascript",
                    "exec": [
                        "if (!pm.environment.get('session_id')) {",
                        "  pm.environment.set('session_id', pm.variables.replaceIn('{{$guid}}'));",
                        "}",
                    ],
                },
            },
            {
                "listen": "test",
                "script": {
                    "type": "text/javascript",
                    "exec": [
                        "if (pm.response.code < 200 || pm.response.code >= 300) return;",
                        "try {",
                        "  const body = pm.response.json();",
                        "  if (body.data) {",
                        "    const d = body.data;",
                        "    if (d.id && !d.session) pm.environment.set('session_id', d.id);",
                        "    if (d.session && d.session.id) pm.environment.set('session_id', d.session.id);",
                        "    if (Array.isArray(d) && d.length && d[d.length-1].id) {",
                        "      pm.environment.set('message_id', d[d.length-1].id);",
                        "    }",
                        "    if (d.messages && d.messages.length) {",
                        "      const last = d.messages[d.messages.length-1];",
                        "      if (last.id) pm.environment.set('message_id', last.id);",
                        "    }",
                        "  }",
                        "} catch (e) {}",
                    ],
                },
            },
        ],
        "variable": [
            {"key": "public_base_url", "value": "https://am.asrax.in"},
            {"key": "gateway_url", "value": "https://am.asrax.in/ai"},
            {"key": "identity_base_url", "value": "https://am.asrax.in"},
            {"key": "keycloak_url", "value": "https://auth.asrax.in/auth"},
            {"key": "keycloak_realm", "value": "am-realm"},
            {"key": "base_url", "value": "http://127.0.0.1:8115"},
            {"key": "product_id", "value": "am_app"},
            {"key": "agent_type", "value": "fin_portfolio"},
        ],
        "item": [
            {
                "name": "00 Auth (run first)",
                "item": [
                    req(
                        "Password Login (am-identity)",
                        "POST",
                        "{{identity_base_url}}/identity/auth/login",
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={
                            "mode": "raw",
                            "raw": '{\n  "username": "{{test_email}}",\n  "password": "{{test_password}}"\n}',
                            "options": {"raw": {"language": "json"}},
                        },
                        event=login_tests,
                        description="User JWT. Saves access_token + user_sub. Use this in browser.",
                    ),
                    req(
                        "Client Credentials (am-gateway-client)",
                        "POST",
                        "{{keycloak_url}}/realms/{{keycloak_realm}}/protocol/openid-connect/token",
                        header=[{"key": "Content-Type", "value": "application/x-www-form-urlencoded"}],
                        body={
                            "mode": "urlencoded",
                            "urlencoded": [
                                {"key": "grant_type", "value": "client_credentials"},
                                {"key": "client_id", "value": "{{gateway_client_id}}"},
                                {"key": "client_secret", "value": "{{gateway_client_secret}}"},
                            ],
                        },
                        event=svc_tests,
                        description="Service JWT for /internal/* (port-forward only).",
                    ),
                    req(
                        "Client Credentials (am-fin-agent-service)",
                        "POST",
                        "{{keycloak_url}}/realms/{{keycloak_realm}}/protocol/openid-connect/token",
                        header=[{"key": "Content-Type", "value": "application/x-www-form-urlencoded"}],
                        body={
                            "mode": "urlencoded",
                            "urlencoded": [
                                {"key": "grant_type", "value": "client_credentials"},
                                {"key": "client_id", "value": "{{fin_agent_client_id}}"},
                                {"key": "client_secret", "value": "{{fin_agent_client_secret}}"},
                            ],
                        },
                        event=svc_tests,
                        description="Optional alternate service JWT. Needs fin_agent_client_secret in env.",
                    ),
                ],
            },
            {
                "name": "01 Health + Internal (port-forward only)",
                "description": "Browser Postman cannot reach 127.0.0.1. Use desktop + kubectl port-forward, or skip.",
                "item": [
                    req("GET Health", "GET", "{{base_url}}/health"),
                    req("GET Ready", "GET", "{{base_url}}/ready"),
                    req(
                        "POST Append Messages (no auth → 401)",
                        "POST",
                        "{{base_url}}/internal/ai/sessions/{{session_id}}/messages",
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={
                            "mode": "raw",
                            "raw": '{\n  "user_id": "{{user_sub}}",\n  "product_id": "{{product_id}}",\n  "agent_type": "{{agent_type}}",\n  "messages": [{"role": "user", "content": "noauth"}]\n}',
                        },
                    ),
                    req(
                        "POST Append Messages",
                        "POST",
                        "{{base_url}}/internal/ai/sessions/{{session_id}}/messages",
                        auth=bearer_auth("service_access_token"),
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={
                            "mode": "raw",
                            "raw": (
                                '{\n  "user_id": "{{user_sub}}",\n  "product_id": "{{product_id}}",\n'
                                '  "agent_type": "{{agent_type}}",\n  "channel": "user_app",\n'
                                '  "messages": [\n    {"role": "user", "content": "Show portfolio"},\n'
                                '    {"role": "assistant", "content": "Here is a summary", "tokens_used": 100}\n  ]\n}'
                            ),
                        },
                    ),
                    req(
                        "GET Session Context",
                        "GET",
                        "{{base_url}}/internal/ai/sessions/{{session_id}}/context?user_id={{user_sub}}&limit=20",
                        auth=bearer_auth("service_access_token"),
                    ),
                ],
            },
            {
                "name": "02 User Sessions (public — browser OK)",
                "description": "https://am.asrax.in/v1/user-platform — works in browser Postman with user JWT.",
                "item": [
                    req(
                        "GET List Sessions",
                        "GET",
                        "{{public_base_url}}/v1/user-platform/ai/sessions?product_id={{product_id}}&agent_type={{agent_type}}",
                        auth=bearer_auth("access_token"),
                    ),
                    req(
                        "POST Create Session",
                        "POST",
                        "{{public_base_url}}/v1/user-platform/ai/sessions",
                        auth=bearer_auth("access_token"),
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={
                            "mode": "raw",
                            "raw": (
                                '{\n  "product_id": "{{product_id}}",\n  "agent_type": "{{agent_type}}",\n'
                                '  "title": "Postman browser session"\n}'
                            ),
                        },
                    ),
                    req(
                        "GET Session Detail",
                        "GET",
                        "{{public_base_url}}/v1/user-platform/ai/sessions/{{session_id}}",
                        auth=bearer_auth("access_token"),
                    ),
                    req(
                        "PATCH Rename Session",
                        "PATCH",
                        "{{public_base_url}}/v1/user-platform/ai/sessions/{{session_id}}",
                        auth=bearer_auth("access_token"),
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={"mode": "raw", "raw": '{\n  "title": "Renamed in Postman"\n}'},
                    ),
                    req(
                        "DELETE Session",
                        "DELETE",
                        "{{public_base_url}}/v1/user-platform/ai/sessions/{{session_id}}",
                        auth=bearer_auth("access_token"),
                    ),
                ],
            },
            {
                "name": "03 Gateway Sessions (Flutter path — browser OK)",
                "description": "https://am.asrax.in/ai/v1/ai/sessions* — same APIs the app will call.",
                "item": [
                    req(
                        "GET Gateway Health",
                        "GET",
                        "{{gateway_url}}/v1/ai/health",
                    ),
                    req(
                        "GET List Sessions via Gateway",
                        "GET",
                        "{{gateway_url}}/v1/ai/sessions?product_id={{product_id}}&agent_type={{agent_type}}",
                        auth=bearer_auth("access_token"),
                    ),
                    req(
                        "POST Create Session via Gateway",
                        "POST",
                        "{{gateway_url}}/v1/ai/sessions",
                        auth=bearer_auth("access_token"),
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={
                            "mode": "raw",
                            "raw": (
                                '{\n  "product_id": "{{product_id}}",\n  "agent_type": "{{agent_type}}",\n'
                                '  "title": "Gateway Postman session"\n}'
                            ),
                        },
                    ),
                    req(
                        "GET Session via Gateway",
                        "GET",
                        "{{gateway_url}}/v1/ai/sessions/{{session_id}}",
                        auth=bearer_auth("access_token"),
                    ),
                    req(
                        "PATCH Rename via Gateway",
                        "PATCH",
                        "{{gateway_url}}/v1/ai/sessions/{{session_id}}",
                        auth=bearer_auth("access_token"),
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={"mode": "raw", "raw": '{\n  "title": "Gateway renamed"\n}'},
                    ),
                    req(
                        "DELETE Session via Gateway",
                        "DELETE",
                        "{{gateway_url}}/v1/ai/sessions/{{session_id}}",
                        auth=bearer_auth("access_token"),
                    ),
                ],
            },
            {
                "name": "04 Feedback (browser OK)",
                "item": [
                    req(
                        "POST Feedback (public user-platform)",
                        "POST",
                        "{{public_base_url}}/v1/user-platform/ai/feedback",
                        auth=bearer_auth("access_token"),
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={
                            "mode": "raw",
                            "raw": (
                                '{\n  "session_id": "{{session_id}}",\n  "agent_type": "{{agent_type}}",\n'
                                '  "rating": "down",\n  "comment": "postman"\n}'
                            ),
                        },
                    ),
                    req(
                        "POST Feedback via Gateway",
                        "POST",
                        "{{gateway_url}}/v1/ai/feedback",
                        auth=bearer_auth("access_token"),
                        header=[{"key": "Content-Type", "value": "application/json"}],
                        body={
                            "mode": "raw",
                            "raw": (
                                '{\n  "sessionId": "{{session_id}}",\n  "rating": "thumbs_down",\n'
                                '  "comment": "gateway postman"\n}'
                            ),
                        },
                    ),
                ],
            },
        ],
    }


def env_values(
    *,
    name_hint: str,
    base_url: str,
    gateway_secret: str,
    fin_secret: str,
    test_email: str,
    test_password: str,
) -> list[dict]:
    return [
        {"enabled": True, "key": "public_base_url", "value": "https://am.asrax.in", "type": "default"},
        {"enabled": True, "key": "gateway_url", "value": "https://am.asrax.in/ai", "type": "default"},
        {"enabled": True, "key": "identity_base_url", "value": "https://am.asrax.in", "type": "default"},
        {"enabled": True, "key": "keycloak_url", "value": "https://auth.asrax.in/auth", "type": "default"},
        {"enabled": True, "key": "keycloak_realm", "value": "am-realm", "type": "default"},
        {"enabled": True, "key": "base_url", "value": base_url, "type": "default"},
        {"enabled": True, "key": "gateway_client_id", "value": "am-gateway-client", "type": "default"},
        {"enabled": True, "key": "gateway_client_secret", "value": gateway_secret, "type": "secret"},
        {"enabled": True, "key": "fin_agent_client_id", "value": "am-fin-agent-service", "type": "default"},
        {"enabled": True, "key": "fin_agent_client_secret", "value": fin_secret, "type": "secret"},
        {"enabled": True, "key": "test_email", "value": test_email, "type": "default"},
        {"enabled": True, "key": "test_password", "value": test_password, "type": "secret"},
        {"enabled": True, "key": "access_token", "value": "", "type": "secret"},
        {"enabled": True, "key": "service_access_token", "value": "", "type": "secret"},
        {"enabled": True, "key": "user_sub", "value": "", "type": "default"},
        {"enabled": True, "key": "session_id", "value": "", "type": "default"},
        {"enabled": True, "key": "message_id", "value": "", "type": "default"},
        {"enabled": True, "key": "product_id", "value": "am_app", "type": "default"},
        {"enabled": True, "key": "agent_type", "value": "fin_portfolio", "type": "default"},
        {"enabled": True, "key": "env_note", "value": name_hint, "type": "default"},
    ]


def main() -> None:
    creds = load_creds()
    api_key = creds.get("POSTMAN_API_KEY")
    if not api_key:
        raise SystemExit("POSTMAN_API_KEY missing")
    kc, tok = admin_token(creds)
    gw_secret = client_secret(kc, tok, "am-gateway-client")
    fin_secret = client_secret(kc, tok, "am-fin-agent-service")
    email = "test.user@example.com"
    password = reset_test_password(kc, tok, email)
    print("ok secrets fetched (not printed)")

    collection = build_collection()
    POSTMAN_DIR.mkdir(parents=True, exist_ok=True)
    (POSTMAN_DIR / "AM-User-Platform.postman_collection.json").write_text(
        json.dumps(collection, indent=2), encoding="utf-8"
    )

    pm_headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

    # Update collection (put needs id fields stripped for recreate — use Prefer async)
    # Fetch existing to preserve IDs is hard; put without item ids recreates.
    code, body = http_json(
        "PUT",
        f"https://api.getpostman.com/collections/{COLLECTION_UID}",
        pm_headers,
        {"collection": collection},
    )
    print(f"ok put collection HTTP {code}")

    # Update port-forward env (keep for laptop)
    code, body = http_json(
        "PUT",
        f"https://api.getpostman.com/environments/{PORT_FORWARD_ENV_UID}",
        pm_headers,
        {
            "environment": {
                "name": "AM User Platform — Prod Port-Forward",
                "values": env_values(
                    name_hint="laptop+kubectl port-forward 8115",
                    base_url="http://127.0.0.1:8115",
                    gateway_secret=gw_secret,
                    fin_secret=fin_secret,
                    test_email=email,
                    test_password=password,
                ),
            }
        },
    )
    print(f"ok put port-forward env HTTP {code}")

    # Create / replace browser env
    browser_name = "AM User Platform — Prod Public (Browser)"
    code, envs = http_json(
        "GET",
        f"https://api.getpostman.com/environments?workspace={WORKSPACE}",
        {"X-Api-Key": api_key},
    )
    browser_uid = None
    if code == 200 and isinstance(envs, dict):
        for e in envs.get("environments") or []:
            if e.get("name") == browser_name:
                browser_uid = e.get("uid")
                break
    browser_payload = {
        "environment": {
            "name": browser_name,
            "values": env_values(
                name_hint="browser Postman — use public + gateway URLs",
                base_url="https://am.asrax.in",  # health won't work; user routes use public_base_url
                gateway_secret=gw_secret,
                fin_secret=fin_secret,
                test_email=email,
                test_password=password,
            ),
        }
    }
    if browser_uid:
        code, body = http_json(
            "PUT",
            f"https://api.getpostman.com/environments/{browser_uid}",
            pm_headers,
            browser_payload,
        )
        print(f"ok put browser env HTTP {code} uid={browser_uid}")
    else:
        code, body = http_json(
            "POST",
            f"https://api.getpostman.com/environments?workspace={WORKSPACE}",
            pm_headers,
            browser_payload,
        )
        browser_uid = (body.get("environment") or {}).get("uid") if isinstance(body, dict) else None
        print(f"ok create browser env HTTP {code} uid={browser_uid}")

    ids = {
        "collection_uid": COLLECTION_UID,
        "environment_uid_port_forward": PORT_FORWARD_ENV_UID,
        "environment_uid_browser": browser_uid,
        "workspace": WORKSPACE,
        "test_email": email,
    }
    (POSTMAN_DIR / "_postman_ids.json").write_text(json.dumps(ids, indent=2), encoding="utf-8")
    (POSTMAN_DIR / "AM-User-Platform.browser.postman_environment.json").write_text(
        json.dumps(
            {
                "id": "am-user-platform-browser-env",
                "name": browser_name,
                "values": [
                    {**v, "value": "" if v["type"] == "secret" else v["value"]}
                    for v in browser_payload["environment"]["values"]
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("DONE — select browser env in Postman top-right, then run 00 Auth")


if __name__ == "__main__":
    main()

"""Upload AM User Platform collection/env to Postman and smoke-test via port-forward.

Never prints secret values. Requires:
  - POSTMAN_API_KEY in ~/.asrax/credentials.env
  - Keycloak admin in credentials.env (to fetch gateway client secret)
  - kubectl port-forward already listening on 127.0.0.1:8115 (or starts checks only)
"""

from __future__ import annotations

import base64
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

HOME = pathlib.Path.home()
CREDS = HOME / ".asrax" / "credentials.env"
WORKSPACE = "c1ed9ba4-e485-4377-8374-7685abf4247d"
COLLECTION_JSON = (
    pathlib.Path(__file__).resolve().parents[1]
    / "postman"
    / "_upload_payload.json"
)
IDS_OUT = pathlib.Path(__file__).resolve().parents[1] / "postman" / "_postman_ids.json"
BASE = "http://127.0.0.1:8115"
KC_REALM = "am-realm"


def load_creds() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in CREDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"')
    return out


def http_json(method: str, url: str, headers: dict, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode(errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {err[:400]}") from e


def ok(msg: str) -> None:
    print(f"[ok] {msg}")


def fail(msg: str) -> None:
    print(f"[fail] {msg}")
    raise SystemExit(1)


def main() -> None:
    creds = load_creds()
    api_key = creds.get("POSTMAN_API_KEY") or creds.get("POSTMAN_KEY")
    if not api_key:
        fail("POSTMAN_API_KEY missing")

    kc_url = (creds.get("KEYCLOAK_URL") or "http://auth.munish.org/auth").rstrip("/")
    kc_admin = creds.get("KEYCLOAK_ADMIN")
    kc_pass = creds.get("KEYCLOAK_ADMIN_PASSWORD")
    if not kc_admin or not kc_pass:
        fail("KEYCLOAK_ADMIN / KEYCLOAK_ADMIN_PASSWORD missing")

    # Gateway client secret via Keycloak admin
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": kc_admin,
            "password": kc_pass,
        }
    ).encode()
    req = urllib.request.Request(
        f"{kc_url}/realms/master/protocol/openid-connect/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        token = json.loads(resp.read().decode())["access_token"]
    hdr = {"Authorization": f"Bearer {token}"}
    clients = http_json(
        "GET",
        f"{kc_url}/admin/realms/{KC_REALM}/clients?clientId=am-gateway-client&max=1",
        hdr,
    )
    if not clients:
        fail("am-gateway-client not found")
    client_uuid = clients[0]["id"]
    secret_obj = http_json(
        "GET",
        f"{kc_url}/admin/realms/{KC_REALM}/clients/{client_uuid}/client-secret",
        hdr,
    )
    gateway_secret = secret_obj.get("value")
    if not gateway_secret:
        fail("empty gateway client secret")
    ok("fetched am-gateway-client secret from Keycloak")

    collection = json.loads(COLLECTION_JSON.read_text(encoding="utf-8"))
    created = http_json(
        "POST",
        f"https://api.getpostman.com/collections?workspace={WORKSPACE}",
        {"X-Api-Key": api_key, "Content-Type": "application/json"},
        {"collection": collection},
    )
    col = created.get("collection") or {}
    col_uid = col.get("uid") or col.get("id")
    if not col_uid:
        fail(f"collection create missing uid: {list(created.keys())}")
    ok(f"Postman collection created: {col.get('name')} ({col_uid})")

    env_body = {
        "environment": {
            "name": "AM User Platform — Prod Port-Forward",
            "values": [
                {"key": "base_url", "value": BASE, "type": "default", "enabled": True},
                {
                    "key": "keycloak_url",
                    "value": kc_url,
                    "type": "default",
                    "enabled": True,
                },
                {
                    "key": "keycloak_realm",
                    "value": KC_REALM,
                    "type": "default",
                    "enabled": True,
                },
                {
                    "key": "gateway_client_id",
                    "value": "am-gateway-client",
                    "type": "default",
                    "enabled": True,
                },
                {
                    "key": "gateway_client_secret",
                    "value": gateway_secret,
                    "type": "secret",
                    "enabled": True,
                },
                {
                    "key": "fin_agent_client_id",
                    "value": "am-fin-agent-service",
                    "type": "default",
                    "enabled": True,
                },
                {
                    "key": "fin_agent_client_secret",
                    "value": "",
                    "type": "secret",
                    "enabled": True,
                },
                {
                    "key": "test_email",
                    "value": "test.user@example.com",
                    "type": "default",
                    "enabled": True,
                },
                {
                    "key": "test_password",
                    "value": "TestPass123!",
                    "type": "secret",
                    "enabled": True,
                },
                {"key": "access_token", "value": "", "type": "secret", "enabled": True},
                {
                    "key": "service_access_token",
                    "value": "",
                    "type": "secret",
                    "enabled": True,
                },
                {"key": "user_sub", "value": "", "type": "default", "enabled": True},
                {"key": "session_id", "value": "", "type": "default", "enabled": True},
                {"key": "message_id", "value": "", "type": "default", "enabled": True},
                {"key": "product_id", "value": "am_app", "type": "default", "enabled": True},
                {
                    "key": "agent_type",
                    "value": "fin_portfolio",
                    "type": "default",
                    "enabled": True,
                },
            ],
        }
    }
    env_created = http_json(
        "POST",
        f"https://api.getpostman.com/environments?workspace={WORKSPACE}",
        {"X-Api-Key": api_key, "Content-Type": "application/json"},
        env_body,
    )
    env = env_created.get("environment") or {}
    env_uid = env.get("uid") or env.get("id")
    if not env_uid:
        fail("environment create missing uid")
    ok(f"Postman environment created: {env.get('name')} ({env_uid})")
    IDS_OUT.write_text(
        json.dumps(
            {
                "collection_uid": col_uid,
                "environment_uid": env_uid,
                "workspace": WORKSPACE,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ok(f"wrote {IDS_OUT.name}")

    # --- Smoke against local port-forward ---
    results: list[tuple[str, bool, str]] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        results.append((name, cond, detail))
        print(f"[{'pass' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))

    def get(path: str, headers: dict | None = None) -> tuple[int, dict | str]:
        req = urllib.request.Request(BASE + path, headers=headers or {}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode()
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, raw

    def post(
        path: str, body: dict | None = None, headers: dict | None = None, form: dict | None = None
    ) -> tuple[int, dict | str]:
        hdrs = dict(headers or {})
        data = None
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        elif body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, raw

    def patch(path: str, body: dict, headers: dict) -> tuple[int, dict | str]:
        data = json.dumps(body).encode()
        hdrs = dict(headers)
        hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                try:
                    return resp.status, json.loads(raw)
                except json.JSONDecodeError:
                    return resp.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                return e.code, json.loads(raw)
            except json.JSONDecodeError:
                return e.code, raw

    # Health
    code, body = get("/health")
    check("Health Check", code == 200 and isinstance(body, dict) and body.get("status") == "ok")
    code, body = get("/ready")
    check(
        "Ready Check",
        code == 200
        and isinstance(body, dict)
        and body.get("database") is True,
        f"database={body.get('database') if isinstance(body, dict) else '?'}",
    )

    # Service token
    form = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": "am-gateway-client",
            "client_secret": gateway_secret,
        }
    ).encode()
    req = urllib.request.Request(
        f"{kc_url}/realms/{KC_REALM}/protocol/openid-connect/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            svc = json.loads(resp.read().decode())
        service_token = svc.get("access_token")
        check("Client Credentials (gateway)", bool(service_token))
    except Exception as e:
        service_token = None
        check("Client Credentials (gateway)", False, type(e).__name__)

    # User token
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "am-web-client",
            "username": "test.user@example.com",
            "password": "TestPass123!",
        }
    ).encode()
    req = urllib.request.Request(
        f"{kc_url}/realms/{KC_REALM}/protocol/openid-connect/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    user_sub = None
    access_token = None
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            user = json.loads(resp.read().decode())
        access_token = user.get("access_token")
        if access_token:
            payload = access_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            user_sub = json.loads(base64.urlsafe_b64decode(payload)).get("sub")
        check("Password Login (am-web-client)", bool(access_token and user_sub))
    except urllib.error.HTTPError as e:
        check("Password Login (am-web-client)", False, f"HTTP {e.code}")
    except Exception as e:
        check("Password Login (am-web-client)", False, type(e).__name__)

    # 401 without auth
    code, _ = post(
        "/internal/ai/sessions/00000000-0000-0000-0000-000000000001/messages",
        body={
            "user_id": "x",
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    check("Append Messages — no auth (expect 401)", code == 401, f"got {code}")

    session_id = str(uuid.uuid4())
    message_id = None
    if service_token and user_sub:
        code, body = post(
            f"/internal/ai/sessions/{session_id}/messages",
            body={
                "user_id": user_sub,
                "product_id": "am_app",
                "agent_type": "fin_portfolio",
                "messages": [
                    {"role": "user", "content": "hello from postman smoke"},
                    {
                        "role": "assistant",
                        "content": "hi back",
                        "tokens_used": 12,
                    },
                ],
            },
            headers={"Authorization": f"Bearer {service_token}"},
        )
        ok_append = code in (200, 201) and isinstance(body, dict)
        check("Append Messages", ok_append, f"HTTP {code}")
        if ok_append:
            data = body.get("data")
            if isinstance(data, list) and data:
                message_id = data[0].get("id")
            elif isinstance(data, dict):
                message_id = (data.get("messages") or [{}])[-1].get("id")

        code, body = get(
            f"/internal/ai/sessions/{session_id}/context?user_id={urllib.parse.quote(user_sub)}&limit=20",
            headers={"Authorization": f"Bearer {service_token}"},
        )
        ctx_ok = code == 200 and isinstance(body, dict)
        msgs = []
        if ctx_ok:
            d = body.get("data") or {}
            msgs = d.get("messages") or d.get("items") or []
            if isinstance(d, list):
                msgs = d
        check(
            "Get Session Context",
            ctx_ok and len(msgs) >= 2,
            f"HTTP {code} msgs={len(msgs) if isinstance(msgs, list) else '?'}",
        )

    if access_token:
        auth = {"Authorization": f"Bearer {access_token}"}
        code, body = get(
            "/v1/user-platform/ai/sessions?product_id=am_app&agent_type=fin_portfolio",
            headers=auth,
        )
        check("List Sessions", code == 200, f"HTTP {code}")

        code, body = get(
            f"/v1/user-platform/ai/sessions/{session_id}",
            headers=auth,
        )
        check("Get Session", code == 200, f"HTTP {code}")

        code, body = patch(
            f"/v1/user-platform/ai/sessions/{session_id}",
            {"title": "Postman smoke"},
            headers=auth,
        )
        check("Rename Session", code == 200, f"HTTP {code}")

        if message_id or True:
            fb = {
                "session_id": session_id,
                "rating": -1,
                "comment": "smoke feedback",
            }
            if message_id:
                fb["message_id"] = message_id
            code, body = post(
                "/v1/user-platform/ai/feedback",
                body=fb,
                headers=auth,
            )
            check("Submit Feedback", code in (200, 201), f"HTTP {code}")

    failed = [n for n, p, _ in results if not p]
    print()
    print(f"SMOKE: {len(results) - len(failed)}/{len(results)} passed")
    if failed:
        print("Failed:", ", ".join(failed))
        raise SystemExit(2)
    print("ALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()

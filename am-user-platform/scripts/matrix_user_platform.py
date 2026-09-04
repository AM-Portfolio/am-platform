"""Full user-platform endpoint matrix (port-forward + public ingress). Never prints secrets."""

from __future__ import annotations

import base64
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request
import uuid

CREDS = pathlib.Path.home() / ".asrax" / "credentials.env"
PF = os.environ.get("BASE_URL", "http://127.0.0.1:8115").rstrip("/")
PUBLIC = os.environ.get("PUBLIC_BASE_URL", "https://am.asrax.in").rstrip("/")
KEYCLOAK = os.environ.get("KEYCLOAK_URL", "https://auth.asrax.in/auth").rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM", "am-realm")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def load_creds() -> dict[str, str]:
    out: dict[str, str] = {}
    if CREDS.exists():
        for line in CREDS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def req(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    hdrs = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:
        return 0, {"error": type(e).__name__, "msg": str(e)[:120]}


def token_form_admin(kc_url: str, username: str, password: str) -> str:
    data = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": username,
            "password": password,
        }
    ).encode()
    code, body = req(
        "POST",
        f"{kc_url}/realms/master/protocol/openid-connect/token",
        {"Content-Type": "application/x-www-form-urlencoded"},
        data,
    )
    if code != 200 or not isinstance(body, dict) or not body.get("access_token"):
        raise RuntimeError(f"admin token HTTP {code}")
    return body["access_token"]


def fetch_client_secret(kc_url: str, admin_token: str, client_id: str) -> str:
    code, body = req(
        "GET",
        f"{kc_url}/admin/realms/{REALM}/clients?clientId={urllib.parse.quote(client_id)}&max=1",
        {"Authorization": f"Bearer {admin_token}"},
    )
    if code != 200 or not isinstance(body, list) or not body:
        raise RuntimeError(f"client lookup HTTP {code}")
    client_uuid = body[0]["id"]
    code, secret_obj = req(
        "GET",
        f"{kc_url}/admin/realms/{REALM}/clients/{client_uuid}/client-secret",
        {"Authorization": f"Bearer {admin_token}"},
    )
    if code != 200 or not isinstance(secret_obj, dict):
        raise RuntimeError(f"client secret HTTP {code}")
    return secret_obj.get("value") or ""


def rotate_test_user_password(kc_url: str, admin_token: str, email: str) -> str:
    q = urllib.parse.urlencode({"email": email, "exact": "true"})
    code, users = req(
        "GET",
        f"{kc_url}/admin/realms/{REALM}/users?{q}",
        {"Authorization": f"Bearer {admin_token}"},
    )
    if code != 200 or not isinstance(users, list) or not users:
        raise RuntimeError(f"user lookup HTTP {code}")
    user_id = users[0]["id"]
    new_pw = "Tmp" + uuid.uuid4().hex[:12] + "9A"
    payload = json.dumps(
        {"type": "password", "value": new_pw, "temporary": False}
    ).encode()
    code, _ = req(
        "PUT",
        f"{kc_url}/admin/realms/{REALM}/users/{user_id}/reset-password",
        {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
        payload,
    )
    if code not in (204, 200):
        raise RuntimeError(f"reset-password HTTP {code}")
    return new_pw


def jwt_sub(token: str) -> str:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))["sub"]


def main() -> None:
    creds = load_creds()
    kc_url = (os.environ.get("KEYCLOAK_URL") or creds.get("KEYCLOAK_URL") or KEYCLOAK).rstrip("/")
    kc_admin = creds.get("KEYCLOAK_ADMIN") or ""
    kc_pass = creds.get("KEYCLOAK_ADMIN_PASSWORD") or ""
    if not kc_admin or not kc_pass:
        raise SystemExit("FAIL: KEYCLOAK_ADMIN missing in credentials.env")

    admin_token = token_form_admin(kc_url, kc_admin, kc_pass)
    gw_secret = fetch_client_secret(kc_url, admin_token, "am-gateway-client")
    email = os.environ.get("TEST_EMAIL") or "test.user@example.com"
    password = os.environ.get("TEST_PASSWORD") or rotate_test_user_password(
        kc_url, admin_token, email
    )
    if not gw_secret or not password:
        raise SystemExit("FAIL: could not obtain gateway secret or test user password")

    passed = 0
    total = 0

    def run(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, total
        total += 1
        print(f"[{'pass' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if cond:
            passed += 1

    code, body = req("GET", f"{PF}/health")
    run("GET /health", code == 200 and isinstance(body, dict) and body.get("status") == "ok")

    code, body = req("GET", f"{PF}/health/live")
    run("GET /health/live", code == 200 and isinstance(body, dict) and body.get("status") == "ok")

    code, body = req("GET", f"{PF}/ready")
    run(
        "GET /ready database=true",
        code == 200 and isinstance(body, dict) and body.get("database") is True,
        f"HTTP {code}",
    )

    sid = str(uuid.uuid4())
    code, _ = req(
        "POST",
        f"{PF}/internal/ai/sessions/{sid}/messages",
        {"Content-Type": "application/json"},
        json.dumps(
            {
                "user_id": "x",
                "product_id": "am_app",
                "agent_type": "fin_portfolio",
                "messages": [{"role": "user", "content": "noauth"}],
            }
        ).encode(),
    )
    run("internal append no auth → 401", code == 401, f"got {code}")

    code, _ = req("GET", f"{PF}/v1/user-platform/ai/sessions")
    run("user list no auth → 401", code == 401, f"got {code}")

    token_body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": "am-gateway-client",
            "client_secret": gw_secret,
        }
    ).encode()
    code, body = req(
        "POST",
        f"{KEYCLOAK}/realms/{REALM}/protocol/openid-connect/token",
        {"Content-Type": "application/x-www-form-urlencoded"},
        token_body,
    )
    svc = body.get("access_token") if isinstance(body, dict) else None
    run("gateway client credentials", bool(svc), f"HTTP {code}")

    code, body = req(
        "POST",
        f"{PUBLIC}/identity/auth/login",
        {"Content-Type": "application/json"},
        json.dumps({"username": email, "password": password}).encode(),
    )
    user = body.get("access_token") if isinstance(body, dict) else None
    sub = jwt_sub(user) if user else ""
    run("identity login", bool(user and sub), f"HTTP {code}")

    auth_svc = {"Authorization": f"Bearer {svc}", "Content-Type": "application/json"} if svc else {}
    auth_user = {"Authorization": f"Bearer {user}", "Content-Type": "application/json"} if user else {}
    other_id = f"other-{uuid.uuid4()}"
    other_sid = str(uuid.uuid4())
    message_id = None

    if svc and sub:
        code, body = req(
            "POST",
            f"{PF}/internal/ai/sessions/{sid}/messages",
            auth_svc,
            json.dumps(
                {
                    "user_id": sub,
                    "product_id": "am_app",
                    "agent_type": "fin_portfolio",
                    "channel": "user_app",
                    "messages": [
                        {"role": "user", "content": "matrix user Q"},
                        {
                            "role": "assistant",
                            "content": "matrix assistant A",
                            "tokens_used": 42,
                        },
                    ],
                }
            ).encode(),
        )
        run("POST /internal/ai/sessions/{id}/messages", code in (200, 201), f"HTTP {code}")
        if isinstance(body, dict) and isinstance(body.get("data"), list) and body["data"]:
            message_id = body["data"][-1].get("id")

        q = urllib.parse.urlencode({"user_id": sub, "limit": "20"})
        code, body = req(
            "GET",
            f"{PF}/internal/ai/sessions/{sid}/context?{q}",
            {"Authorization": f"Bearer {svc}"},
        )
        n = 0
        if isinstance(body, dict):
            d = body.get("data") or {}
            n = len(d.get("messages") or []) if isinstance(d, dict) else 0
        run("GET /internal/ai/sessions/{id}/context", code == 200 and n >= 2, f"HTTP {code} msgs={n}")

        other_sid = str(uuid.uuid4())
        code, _ = req(
            "POST",
            f"{PF}/internal/ai/sessions/{other_sid}/messages",
            auth_svc,
            json.dumps(
                {
                    "user_id": other_id,
                    "product_id": "am_app",
                    "agent_type": "fin_portfolio",
                    "messages": [{"role": "user", "content": "secret"}],
                }
            ).encode(),
        )
        run("seed other-user session", code in (200, 201), f"HTTP {code}")

    if user:
        code, body = req(
            "POST",
            f"{PF}/v1/user-platform/ai/sessions",
            auth_user,
            json.dumps(
                {
                    "product_id": "am_app",
                    "agent_type": "fin_portfolio",
                    "title": "Matrix created",
                }
            ).encode(),
        )
        created_id = None
        if isinstance(body, dict):
            created_id = (body.get("data") or {}).get("id")
        run("POST /v1/user-platform/ai/sessions", code == 201 and bool(created_id), f"HTTP {code}")

        code, _ = req(
            "GET",
            f"{PF}/v1/user-platform/ai/sessions?product_id=am_app&agent_type=fin_portfolio",
            {"Authorization": f"Bearer {user}"},
        )
        run("GET list sessions (PF)", code == 200, f"HTTP {code}")

        code, _ = req(
            "GET",
            f"{PUBLIC}/v1/user-platform/ai/sessions?product_id=am_app&agent_type=fin_portfolio",
            {"Authorization": f"Bearer {user}"},
        )
        run("GET list sessions (public ingress)", code == 200, f"HTTP {code}")

        code, body = req("GET", f"{PF}/v1/user-platform/ai/sessions/{sid}", {"Authorization": f"Bearer {user}"})
        msgs = 0
        if isinstance(body, dict):
            msgs = len((body.get("data") or {}).get("messages") or [])
        run("GET session detail", code == 200 and msgs >= 2, f"HTTP {code} msgs={msgs}")

        code, body = req(
            "PATCH",
            f"{PF}/v1/user-platform/ai/sessions/{sid}",
            auth_user,
            json.dumps({"title": "Matrix renamed"}).encode(),
        )
        title_ok = isinstance(body, dict) and (body.get("data") or {}).get("title") == "Matrix renamed"
        run("PATCH rename session", code == 200 and title_ok, f"HTTP {code}")

        fb = {
            "session_id": sid,
            "agent_type": "fin_portfolio",
            "rating": "down",
            "comment": "matrix",
        }
        if message_id:
            fb["message_id"] = message_id
        code, _ = req("POST", f"{PF}/v1/user-platform/ai/feedback", auth_user, json.dumps(fb).encode())
        run("POST feedback", code in (200, 201), f"HTTP {code}")

        code, _ = req(
            "GET",
            f"{PF}/v1/user-platform/ai/sessions/{other_sid}",
            {"Authorization": f"Bearer {user}"},
        )
        run("tenancy GET other user session → 404", code == 404, f"got {code}")

        code, _ = req(
            "DELETE",
            f"{PF}/v1/user-platform/ai/sessions/{other_sid}",
            {"Authorization": f"Bearer {user}"},
        )
        run("tenancy DELETE other user session → 404", code == 404, f"got {code}")

        if created_id:
            code, _ = req(
                "DELETE",
                f"{PF}/v1/user-platform/ai/sessions/{created_id}",
                {"Authorization": f"Bearer {user}"},
            )
            run("DELETE own session", code == 204, f"HTTP {code}")
            code, _ = req(
                "GET",
                f"{PF}/v1/user-platform/ai/sessions/{created_id}",
                {"Authorization": f"Bearer {user}"},
            )
            run("GET after DELETE → 404", code == 404, f"got {code}")

    if svc and other_id:
        code, body = req(
            "DELETE",
            f"{PF}/internal/ai/users/{other_id}/data",
            {"Authorization": f"Bearer {svc}"},
        )
        run("DELETE /internal/ai/users/{id}/data", code == 200, f"HTTP {code}")

    print()
    print(f"MATRIX: {passed}/{total} passed")
    if passed != total:
        raise SystemExit(2)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

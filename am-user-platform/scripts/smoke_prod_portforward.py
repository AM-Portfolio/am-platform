"""Smoke-test am-user-platform against http://127.0.0.1:8115 (port-forward).

Env vars (required):
  GATEWAY_CLIENT_SECRET
  TEST_EMAIL
  TEST_PASSWORD

Optional:
  KEYCLOAK_URL (default http://auth.munish.org/auth)
  KEYCLOAK_REALM (default am-realm)
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8115").rstrip("/")
KEYCLOAK = os.environ.get("KEYCLOAK_URL", "https://auth.munish.org/auth").rstrip("/")
REALM = os.environ.get("KEYCLOAK_REALM", "am-realm")
GW_SECRET = os.environ.get("GATEWAY_CLIENT_SECRET", "")
TEST_EMAIL = os.environ.get("TEST_EMAIL", "test.user@example.com")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "")


def check(name: str, cond: bool, detail: str = "") -> bool:
    print(f"[{'pass' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def req(method: str, url: str, headers: dict | None = None, data: bytes | None = None):
    hdrs = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }
    if headers:
        hdrs.update(headers)
    r = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
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
    except Exception as e:
        return 0, {"error": type(e).__name__, "msg": str(e)[:120]}


def token_form(fields: dict) -> str:
    data = urllib.parse.urlencode(fields).encode()
    code, body = req(
        "POST",
        f"{KEYCLOAK}/realms/{REALM}/protocol/openid-connect/token",
        {"Content-Type": "application/x-www-form-urlencoded"},
        data,
    )
    if code != 200 or not isinstance(body, dict):
        raise RuntimeError(f"token HTTP {code}")
    return body["access_token"]


def main() -> None:
    if not GW_SECRET or not TEST_PASSWORD:
        raise SystemExit("FAIL: set GATEWAY_CLIENT_SECRET and TEST_PASSWORD")

    passed = 0
    total = 0

    def run(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, total
        total += 1
        if check(name, cond, detail):
            passed += 1

    code, body = req("GET", f"{BASE}/health")
    run("Health", code == 200 and isinstance(body, dict) and body.get("status") == "ok")

    code, body = req("GET", f"{BASE}/ready")
    run(
        "Ready database=true",
        code == 200 and isinstance(body, dict) and body.get("database") is True,
        str(body.get("database") if isinstance(body, dict) else body)[:80],
    )

    try:
        svc = token_form(
            {
                "grant_type": "client_credentials",
                "client_id": "am-gateway-client",
                "client_secret": GW_SECRET,
            }
        )
        run("Gateway client credentials", bool(svc))
    except Exception as e:
        svc = ""
        run("Gateway client credentials", False, type(e).__name__)

    try:
        # am-web-client has directAccessGrants disabled in prod — use am-identity.
        code, body = req(
            "POST",
            "https://am.asrax.in/identity/auth/login",
            {"Content-Type": "application/json"},
            json.dumps({"username": TEST_EMAIL, "password": TEST_PASSWORD}).encode(),
        )
        user = body.get("access_token") if isinstance(body, dict) else None
        user_sub = None
        if user:
            payload = user.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            user_sub = json.loads(base64.urlsafe_b64decode(payload))["sub"]
        run("Identity password login", bool(user and user_sub), f"HTTP {code}")
    except Exception as e:
        user = ""
        user_sub = ""
        run("Identity password login", False, type(e).__name__)

    session_id = str(uuid.uuid4())
    code, _ = req(
        "POST",
        f"{BASE}/internal/ai/sessions/{session_id}/messages",
        {"Content-Type": "application/json"},
        json.dumps(
            {
                "user_id": user_sub or "x",
                "product_id": "am_app",
                "agent_type": "fin_portfolio",
                "messages": [{"role": "user", "content": "noauth"}],
            }
        ).encode(),
    )
    run("Internal append without auth -> 401", code == 401, f"got {code}")

    message_id = None
    if svc and user_sub:
        code, body = req(
            "POST",
            f"{BASE}/internal/ai/sessions/{session_id}/messages",
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {svc}",
            },
            json.dumps(
                {
                    "user_id": user_sub,
                    "product_id": "am_app",
                    "agent_type": "fin_portfolio",
                    "channel": "user_app",
                    "messages": [
                        {"role": "user", "content": "Show my portfolio summary"},
                        {
                            "role": "assistant",
                            "content": "Here is your portfolio overview.",
                            "tokens_used": 3842,
                            "tools_used": ["get_portfolio_summary"],
                        },
                    ],
                }
            ).encode(),
        )
        run("Internal append messages", code in (200, 201), f"HTTP {code} {str(body)[:160]}")
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, list) and data:
                message_id = data[-1].get("id")
            elif isinstance(data, dict) and data.get("messages"):
                message_id = data["messages"][-1].get("id")

        q = urllib.parse.urlencode({"user_id": user_sub, "limit": "20"})
        code, body = req(
            "GET",
            f"{BASE}/internal/ai/sessions/{session_id}/context?{q}",
            {"Authorization": f"Bearer {svc}"},
        )
        n = 0
        if isinstance(body, dict):
            d = body.get("data") or {}
            if isinstance(d, dict):
                n = len(d.get("messages") or [])
            elif isinstance(d, list):
                n = len(d)
        run("Internal get context", code == 200 and n >= 2, f"HTTP {code} msgs={n} {str(body)[:120]}")

    if user:
        auth = {"Authorization": f"Bearer {user}"}
        code, _ = req(
            "GET",
            f"{BASE}/v1/user-platform/ai/sessions?product_id=am_app&agent_type=fin_portfolio&limit=50",
            auth,
        )
        run("List sessions", code == 200, f"HTTP {code}")

        code, _ = req("GET", f"{BASE}/v1/user-platform/ai/sessions/{session_id}", auth)
        run("Get session", code == 200, f"HTTP {code}")

        code, _ = req(
            "PATCH",
            f"{BASE}/v1/user-platform/ai/sessions/{session_id}",
            {**auth, "Content-Type": "application/json"},
            json.dumps({"title": "Postman smoke"}).encode(),
        )
        run("Rename session", code == 200, f"HTTP {code}")

        fb = {
            "session_id": session_id,
            "agent_type": "fin_portfolio",
            "rating": "down",
            "comment": "smoke",
        }
        if message_id:
            fb["message_id"] = message_id
        code, _ = req(
            "POST",
            f"{BASE}/v1/user-platform/ai/feedback",
            {**auth, "Content-Type": "application/json"},
            json.dumps(fb).encode(),
        )
        run("Submit feedback", code in (200, 201), f"HTTP {code}")

    print()
    print(f"SMOKE: {passed}/{total} passed")
    if passed != total:
        raise SystemExit(2)
    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://am-preprod.asrax.in/identity"
KC = "https://auth.munish.org/auth"
REALM = "am-preprod-realm"
SECRETS = Path(r"A:\InfraCode\AM-Portfolio-grp\am-platform\.secrets.preprod.env")

results: list[tuple[str, str, str]] = []


def load_secrets() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def req(method: str, url: str, *, data=None, headers=None, timeout=30):
    body = None
    hdrs = {"User-Agent": "am-verify/1.0", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode()
            hdrs.setdefault("Content-Type", "application/json")
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode()
    request = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed, dict(resp.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed, dict(e.headers)


def record(name: str, ok: bool, detail: str):
    status = "PASS" if ok else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}: {detail}")


def main():
    secrets = load_secrets()
    stamp = int(time.time())
    test_email = f"verify.smtp.{stamp}@asrax.in"
    test_password = "VerifyTest1a"

    # B0 health
    for path in ("/health", "/docs", "/openapi.json"):
        code, body, _ = req("GET", BASE + path)
        if path == "/health":
            record(
                "health",
                code == 200 and isinstance(body, dict) and body.get("status") == "ok",
                f"{code} {body}",
            )
        else:
            record(f"probe {path}", code in (200, 401, 403) or code < 500, f"{code}")

    # OpenAPI: branded confirm routes + admin
    code, body, _ = req("GET", BASE + "/openapi.json")
    if code == 200 and isinstance(body, dict):
        paths = body.get("paths") or {}
        for p in (
            "/admin/roles",
            "/admin/users",
            "/auth/password-reset",
            "/auth/password-reset/confirm",
            "/auth/verify-email/resend",
            "/auth/verify-email/confirm",
        ):
            record(
                f"openapi has {p}", p in paths, "present" if p in paths else "missing"
            )
    else:
        record("openapi.json", False, f"{code} {body}")

    # Confirm endpoints must be implemented (400 on bad token, not 501)
    code, body, _ = req(
        "POST",
        BASE + "/auth/password-reset/confirm",
        data={"token": "invalid", "new_password": "VerifyTest1a!"},
    )
    record(
        "auth/password-reset/confirm not 501",
        code == 400,
        f"{code} {body}",
    )
    code, body, _ = req(
        "POST",
        BASE + "/auth/verify-email/confirm",
        data={"token": "invalid"},
    )
    record(
        "auth/verify-email/confirm not 501",
        code == 400,
        f"{code} {body}",
    )

    ui_base = (secrets.get("AUTH_UI_BASE_URL") or "").strip().rstrip("/")
    record(
        "AUTH_UI_BASE_URL for branded links (from Vault/secrets)",
        bool(ui_base),
        ui_base or "(missing — set AUTH_UI_BASE_URL)",
    )
    record(
        "AUTH_EMAIL_TOKEN_SECRET present (local secrets)",
        bool(secrets.get("AUTH_EMAIL_TOKEN_SECRET", "").strip()),
        "set" if secrets.get("AUTH_EMAIL_TOKEN_SECRET", "").strip() else "MISSING",
    )

    # B2 register
    code, body, _ = req(
        "POST",
        BASE + "/auth/register",
        data={
            "email": test_email,
            "password": test_password,
            "first_name": "Verify",
            "last_name": "Bot",
        },
    )
    record("auth/register", code == 201, f"{code} {body}")

    # resend verify (identity branded SMTP — not Keycloak execute-actions)
    code, body, _ = req(
        "POST",
        BASE + "/auth/verify-email/resend",
        data={"email": test_email},
    )
    record(
        "auth/verify-email/resend",
        code == 202,
        f"{code} {body if code != 202 else 'accepted (branded mail if SMTP configured in pod)'}",
    )

    # password reset known + unknown
    code, body, _ = req(
        "POST",
        BASE + "/auth/password-reset",
        data={"email": test_email},
    )
    record("auth/password-reset known", code == 202, f"{code} {body}")
    code, body, _ = req(
        "POST",
        BASE + "/auth/password-reset",
        data={"email": f"nobody.{stamp}@example.com"},
    )
    record("auth/password-reset unknown", code == 202, f"{code} {body}")

    # login may fail if verify_email enforced before login
    code, body, _ = req(
        "POST",
        BASE + "/auth/login",
        data={"username": test_email, "password": test_password},
    )
    record(
        "auth/login new user",
        code in (200, 401, 403),
        f"{code} {body if code != 200 else 'tokens ok'}",
    )

    # Keycloak admin: mark email verified + assign admin for admin API tests
    token_url = f"{KC}/realms/master/protocol/openid-connect/token"
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": secrets["KEYCLOAK_ADMIN_USER"],
            "password": secrets["KEYCLOAK_ADMIN_PASSWORD"],
        }
    ).encode()
    code, body, _ = req(
        "POST",
        token_url,
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if code != 200 or not isinstance(body, dict):
        record("keycloak admin token", False, f"{code} {body}")
        print_summary()
        return
    admin_token = body["access_token"]
    record("keycloak admin token", True, "ok")
    ah = {"Authorization": f"Bearer {admin_token}"}

    # find user
    code, users, _ = req(
        "GET",
        f"{KC}/admin/realms/{REALM}/users?email={urllib.parse.quote(test_email)}&exact=true",
        headers=ah,
    )
    if code != 200 or not users:
        record("keycloak find user", False, f"{code} {users}")
        print_summary()
        return
    user_id = users[0]["id"]
    record("keycloak find user", True, user_id)

    # verify email flag so login works + clear required actions
    code, user, _ = req(
        "GET",
        f"{KC}/admin/realms/{REALM}/users/{user_id}",
        headers=ah,
    )
    user["emailVerified"] = True
    user["requiredActions"] = []
    code, _, _ = req(
        "PUT",
        f"{KC}/admin/realms/{REALM}/users/{user_id}",
        data=user,
        headers=ah,
    )
    record("keycloak force emailVerified", code in (204, 200), f"{code}")

    # assign admin role
    code, role, _ = req(
        "GET",
        f"{KC}/admin/realms/{REALM}/roles/admin",
        headers=ah,
    )
    if code == 200:
        code, _, _ = req(
            "POST",
            f"{KC}/admin/realms/{REALM}/users/{user_id}/role-mappings/realm",
            data=[role],
            headers=ah,
        )
        record("keycloak assign admin", code in (204, 200), f"{code}")
    else:
        record("keycloak assign admin", False, f"role fetch {code}")

    # login as admin user via identity
    code, tokens, _ = req(
        "POST",
        BASE + "/auth/login",
        data={"username": test_email, "password": test_password},
    )
    if code != 200 or not isinstance(tokens, dict):
        record("auth/login admin user", False, f"{code} {tokens}")
        print_summary()
        return
    access = tokens["access_token"]
    record("auth/login admin user", True, "token ok")
    bh = {"Authorization": f"Bearer {access}"}

    # B3 admin APIs
    code, body, _ = req("GET", BASE + "/admin/roles", headers=bh)
    record("GET /admin/roles", code == 200 and isinstance(body, list), f"{code} {body}")

    code, body, _ = req("GET", BASE + "/admin/users?max=5", headers=bh)
    record(
        "GET /admin/users",
        code == 200 and isinstance(body, list),
        f"{code} count={len(body) if isinstance(body, list) else '?'}",
    )

    # non-admin: create second user without admin role
    plain_email = f"verify.user.{stamp}@asrax.in"
    code, body, _ = req(
        "POST",
        BASE + "/auth/register",
        data={
            "email": plain_email,
            "password": test_password,
            "first_name": "Plain",
            "last_name": "User",
        },
    )
    record("register plain user", code == 201, f"{code}")
    code, users, _ = req(
        "GET",
        f"{KC}/admin/realms/{REALM}/users?email={urllib.parse.quote(plain_email)}&exact=true",
        headers=ah,
    )
    if code == 200 and users:
        uid2 = users[0]["id"]
        code, u2, _ = req("GET", f"{KC}/admin/realms/{REALM}/users/{uid2}", headers=ah)
        u2["emailVerified"] = True
        u2["requiredActions"] = []
        req("PUT", f"{KC}/admin/realms/{REALM}/users/{uid2}", data=u2, headers=ah)
    code, tokens2, _ = req(
        "POST",
        BASE + "/auth/login",
        data={"username": plain_email, "password": test_password},
    )
    if code == 200:
        code, body, _ = req(
            "GET",
            BASE + "/admin/roles",
            headers={"Authorization": f"Bearer {tokens2['access_token']}"},
        )
        record("non-admin GET /admin/roles", code == 403, f"{code} {body}")
    else:
        record("non-admin login", False, f"{code} {tokens2}")

    # reject service role via admin API
    code, body, _ = req(
        "POST",
        f"{BASE}/admin/users/{user_id}/roles",
        data={"roles": ["service"]},
        headers=bh,
    )
    record("reject assign service", code == 400, f"{code} {body}")

    # assign viewer ok
    code, body, _ = req(
        "POST",
        f"{BASE}/admin/users/{user_id}/roles",
        data={"roles": ["viewer"]},
        headers=bh,
    )
    record("assign viewer", code == 200, f"{code} {body}")

    print_summary()


def print_summary():
    passed = sum(1 for s, _, _ in results if s == "PASS")
    failed = sum(1 for s, _, _ in results if s == "FAIL")
    print("\n=== SUMMARY ===")
    print(f"PASS={passed} FAIL={failed} TOTAL={len(results)}")
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")


if __name__ == "__main__":
    main()

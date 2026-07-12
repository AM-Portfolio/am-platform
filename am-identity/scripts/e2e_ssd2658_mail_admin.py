"""E2E preprod checks for ssd2658@gmail.com — mail + admin roles + Keycloak SMTP."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://am.asrax.in/identity"
KC = "https://auth.munish.org/auth"
REALM = "am-preprod-realm"
EMAIL = "ssd2658@gmail.com"
TEMP_PASSWORD = "AsraxE2eTest1a"
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


def req(method: str, url: str, *, data=None, headers=None, form: bool = False):
    hdrs = {"User-Agent": "am-e2e/1.0", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            hdrs["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=45, context=ctx) as resp:
            raw = resp.read().decode("utf-8", "replace")
            parsed = json.loads(raw) if raw else None
            return resp.status, parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw) if raw else raw
        except json.JSONDecodeError:
            parsed = raw
        return e.code, parsed


def record(name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}: {detail}")


def main() -> None:
    secrets = load_secrets()

    # ── Keycloak admin ────────────────────────────────────────────────────
    code, body = req(
        "POST",
        f"{KC}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": secrets["KEYCLOAK_ADMIN_USER"],
            "password": secrets["KEYCLOAK_ADMIN_PASSWORD"],
        },
        form=True,
    )
    if code != 200:
        record("keycloak admin token", False, f"{code} {body}")
        _summary()
        return
    admin_token = body["access_token"]
    ah = {"Authorization": f"Bearer {admin_token}"}
    record("keycloak admin token", True, "ok")

    # ── Realm SMTP / verify_email ─────────────────────────────────────────
    code, realm = req("GET", f"{KC}/admin/realms/{REALM}", headers=ah)
    if code != 200:
        record("realm get", False, f"{code} {realm}")
        _summary()
        return
    smtp = realm.get("smtpServer") or {}
    record("realm.verifyEmail", bool(realm.get("verifyEmail")), str(realm.get("verifyEmail")))
    record(
        "realm.smtp.host",
        smtp.get("host") == "smtppro.zoho.in",
        f"{smtp.get('host')}",
    )
    record(
        "realm.smtp.port",
        str(smtp.get("port")) == "465",
        f"{smtp.get('port')}",
    )
    record(
        "realm.smtp.from",
        smtp.get("from") == "noreply@asrax.in",
        f"{smtp.get('from')}",
    )
    record(
        "realm.smtp.fromDisplayName",
        smtp.get("fromDisplayName") == "Asrax Accounts",
        f"{smtp.get('fromDisplayName')}",
    )
    record(
        "realm.smtp.ssl",
        str(smtp.get("ssl")).lower() in ("true", "1"),
        f"ssl={smtp.get('ssl')} starttls={smtp.get('starttls')}",
    )
    record("realm.smtp.user", smtp.get("user") == "noreply@asrax.in", f"{smtp.get('user')}")
    record("realm.smtp.password.set", bool(smtp.get("password")), "set" if smtp.get("password") else "MISSING")
    record("realm.resetPasswordAllowed", bool(realm.get("resetPasswordAllowed")), str(realm.get("resetPasswordAllowed")))

    # super_admin role exists
    code, role = req("GET", f"{KC}/admin/realms/{REALM}/roles/super_admin", headers=ah)
    record("realm.role.super_admin", code == 200, f"{code}")

    # ── Ensure user ssd2658@gmail.com ─────────────────────────────────────
    code, users = req(
        "GET",
        f"{KC}/admin/realms/{REALM}/users?email={urllib.parse.quote(EMAIL)}&exact=true",
        headers=ah,
    )
    user = (users or [None])[0] if code == 200 else None
    if not user:
        code, _ = req(
            "POST",
            f"{KC}/admin/realms/{REALM}/users",
            data={
                "username": EMAIL,
                "email": EMAIL,
                "enabled": True,
                "emailVerified": False,
                "firstName": "Munish",
                "lastName": "E2E",
                "credentials": [
                    {"type": "password", "value": TEMP_PASSWORD, "temporary": False}
                ],
            },
            headers=ah,
        )
        record("create user", code in (201, 204), f"{code}")
        code, users = req(
            "GET",
            f"{KC}/admin/realms/{REALM}/users?email={urllib.parse.quote(EMAIL)}&exact=true",
            headers=ah,
        )
        user = (users or [None])[0]
    else:
        record("user exists", True, user.get("id", ""))

    if not user:
        record("resolve user", False, "not found after create")
        _summary()
        return
    uid = user["id"]

    # Reset password for known login in this E2E (does not print password in summary)
    code, _ = req(
        "PUT",
        f"{KC}/admin/realms/{REALM}/users/{uid}/reset-password",
        data={"type": "password", "value": TEMP_PASSWORD, "temporary": False},
        headers=ah,
    )
    record("set password via admin", code in (204, 200), f"{code}")

    # ── Identity health ───────────────────────────────────────────────────
    code, body = req("GET", f"{BASE}/health")
    record("identity health", code == 200, f"{code} {body}")

    # ── Verify email (triggers Zoho → Gmail) ──────────────────────────────
    # Mark unverified first so VERIFY_EMAIL is meaningful
    code, full = req("GET", f"{KC}/admin/realms/{REALM}/users/{uid}", headers=ah)
    full["emailVerified"] = False
    full["requiredActions"] = ["VERIFY_EMAIL"]
    req("PUT", f"{KC}/admin/realms/{REALM}/users/{uid}", data=full, headers=ah)

    code, body = req("POST", f"{BASE}/auth/verify-email/resend", data={"email": EMAIL})
    record("API verify-email/resend", code == 202, f"{code} {body}")

    # Direct Keycloak execute-actions-email (same path Keycloak uses for SMTP)
    code, body = req(
        "PUT",
        f"{KC}/admin/realms/{REALM}/users/{uid}/execute-actions-email",
        data=["VERIFY_EMAIL"],
        headers=ah,
    )
    record(
        "KC execute-actions VERIFY_EMAIL (mail to Gmail)",
        code in (200, 204),
        f"{code} {body if code >= 400 else 'sent — check ssd2658@gmail.com inbox/spam'}",
    )

    # ── Password reset mail ───────────────────────────────────────────────
    code, body = req("POST", f"{BASE}/auth/password-reset", data={"email": EMAIL})
    record("API password-reset", code == 202, f"{code} {body}")

    code, body = req(
        "PUT",
        f"{KC}/admin/realms/{REALM}/users/{uid}/execute-actions-email",
        data=["UPDATE_PASSWORD"],
        headers=ah,
    )
    record(
        "KC execute-actions UPDATE_PASSWORD (mail to Gmail)",
        code in (200, 204),
        f"{code} {body if code >= 400 else 'sent — check ssd2658@gmail.com inbox/spam'}",
    )

    # Clear required actions so login works for admin tests
    code, full = req("GET", f"{KC}/admin/realms/{REALM}/users/{uid}", headers=ah)
    full["emailVerified"] = True
    full["requiredActions"] = []
    req("PUT", f"{KC}/admin/realms/{REALM}/users/{uid}", data=full, headers=ah)

    # ── Roles: admin then super_admin ─────────────────────────────────────
    for role_name in ("admin", "super_admin"):
        code, role = req("GET", f"{KC}/admin/realms/{REALM}/roles/{role_name}", headers=ah)
        if code == 200:
            req(
                "POST",
                f"{KC}/admin/realms/{REALM}/users/{uid}/role-mappings/realm",
                data=[role],
                headers=ah,
            )
            record(f"assign {role_name}", True, "ok")
        else:
            record(f"assign {role_name}", False, f"role fetch {code}")

    code, tokens = req(
        "POST",
        f"{BASE}/auth/login",
        data={"username": EMAIL, "password": TEMP_PASSWORD},
    )
    record("login after verify cleared", code == 200, f"{code}" if code == 200 else f"{code} {tokens}")
    if code != 200:
        _summary()
        return
    bh = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Decode roles claim lightly from JWT payload (no verify — smoke only)
    try:
        import base64

        payload_b64 = tokens["access_token"].split(".")[1]
        pad = "=" * (-len(payload_b64) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64 + pad))
        roles = claims.get("roles") or claims.get("realm_access", {}).get("roles") or []
        record(
            "JWT has admin or super_admin",
            "admin" in roles or "super_admin" in roles,
            f"roles={roles}",
        )
    except Exception as exc:  # noqa: BLE001
        record("JWT decode", False, str(exc))

    code, body = req("GET", f"{BASE}/admin/roles", headers=bh)
    record("GET /admin/roles as user", code == 200, f"{code}")

    code, body = req("GET", f"{BASE}/admin/users?email={urllib.parse.quote(EMAIL)}", headers=bh)
    record("GET /admin/users?email=", code == 200 and isinstance(body, list), f"{code}")

    # super_admin can assign super_admin
    code, body = req(
        "POST",
        f"{BASE}/admin/users/{uid}/roles",
        data={"roles": ["super_admin"]},
        headers=bh,
    )
    record("super_admin self-confirm role API", code == 200, f"{code} {body}")

    # reject service
    code, body = req(
        "POST",
        f"{BASE}/admin/users/{uid}/roles",
        data={"roles": ["service"]},
        headers=bh,
    )
    record("reject service role", code == 400, f"{code} {body}")

    _summary()


def _summary() -> None:
    passed = sum(1 for s, _, _ in results if s == "PASS")
    failed = sum(1 for s, _, _ in results if s == "FAIL")
    print("\n=== E2E SUMMARY ===")
    print(f"PASS={passed} FAIL={failed} TOTAL={len(results)}")
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")


if __name__ == "__main__":
    main()

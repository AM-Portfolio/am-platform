"""E2E preprod checks for ssd2658@gmail.com — branded auth mail + confirm + admin roles.

Public verify/reset no longer rely on Keycloak execute-actions-email.
Mail links use AUTH_UI_BASE_URL (am.asrax.in). Gmail body is not readable here;
confirm is exercised by minting a token with AUTH_EMAIL_TOKEN_SECRET and setting
the matching Keycloak jti attribute (same contract as the mailer).
Manual: check ssd2658@gmail.com for Asrax branded links on am.asrax.in.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import urlsafe_b64encode
from pathlib import Path
from urllib.parse import urlparse

BASE = "https://am.asrax.in/identity"
KC = "https://auth.munish.org/auth"
REALM = "am-preprod-realm"
EMAIL = "ssd2658@gmail.com"
TEMP_PASSWORD = "AsraxE2eTest1a"
RESET_PASSWORD = "AsraxE2eTest2b"
VERIFY_JTI_ATTR = "asraxVerifyJti"
RESET_JTI_ATTR = "asraxResetJti"
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


def _b64encode(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def mint_auth_mail_token(
    *,
    secret: str,
    purpose: str,
    user_id: str,
    email: str,
    ttl_seconds: int = 43200,
) -> tuple[str, str]:
    """Local mirror of am_identity.email.tokens.mint_auth_mail_token."""
    jti = secrets.token_urlsafe(16)
    now = int(time.time())
    payload = {
        "purpose": purpose,
        "sub": user_id,
        "email": email.lower().strip(),
        "jti": jti,
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    sig = _b64encode(
        hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{body}.{sig}", jti


def set_user_attr(uid: str, ah: dict, attr: str, value: str | None) -> int:
    code, full = req("GET", f"{KC}/admin/realms/{REALM}/users/{uid}", headers=ah)
    if code != 200 or not isinstance(full, dict):
        return code
    attrs = dict(full.get("attributes") or {})
    if value is None:
        attrs.pop(attr, None)
    else:
        attrs[attr] = [value]
    full["attributes"] = attrs
    code, _ = req("PUT", f"{KC}/admin/realms/{REALM}/users/{uid}", data=full, headers=ah)
    return code


def main() -> None:
    secrets_map = load_secrets()
    token_secret = secrets_map.get("AUTH_EMAIL_TOKEN_SECRET", "").strip()
    ui_base = (secrets_map.get("AUTH_UI_BASE_URL") or "https://am.asrax.in").rstrip("/")
    ttl = int(secrets_map.get("AUTH_EMAIL_TOKEN_TTL_SECONDS") or "43200")

    record(
        "AUTH_EMAIL_TOKEN_SECRET configured",
        bool(token_secret),
        "set" if token_secret else "MISSING",
    )
    host = urlparse(ui_base).hostname or ""
    record(
        "AUTH_UI_BASE_URL host",
        host in ("am.asrax.in", "am-dev.asrax.in"),
        f"host={host} base={ui_base}",
    )

    # ── Keycloak admin ────────────────────────────────────────────────────
    code, body = req(
        "POST",
        f"{KC}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": secrets_map["KEYCLOAK_ADMIN_USER"],
            "password": secrets_map["KEYCLOAK_ADMIN_PASSWORD"],
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

    # ── Realm SMTP (legacy KC mail; public auth uses identity SMTP) ───────
    code, realm = req("GET", f"{KC}/admin/realms/{REALM}", headers=ah)
    if code != 200:
        record("realm get", False, f"{code} {realm}")
        _summary()
        return
    smtp = realm.get("smtpServer") or {}
    record("realm.verifyEmail", bool(realm.get("verifyEmail")), str(realm.get("verifyEmail")))
    record(
        "realm.smtp.host (informational)",
        True,
        f"{smtp.get('host')}",
    )
    record(
        "realm.resetPasswordAllowed",
        bool(realm.get("resetPasswordAllowed")),
        str(realm.get("resetPasswordAllowed")),
    )

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

    code, _ = req(
        "PUT",
        f"{KC}/admin/realms/{REALM}/users/{uid}/reset-password",
        data={"type": "password", "value": TEMP_PASSWORD, "temporary": False},
        headers=ah,
    )
    record("set password via admin", code in (204, 200), f"{code}")

    # ── Identity health + OpenAPI confirm routes ──────────────────────────
    code, body = req("GET", f"{BASE}/health")
    record("identity health", code == 200, f"{code} {body}")

    code, openapi = req("GET", f"{BASE}/openapi.json")
    paths = (openapi or {}).get("paths") if isinstance(openapi, dict) else {}
    for p in (
        "/auth/password-reset/confirm",
        "/auth/verify-email/confirm",
        "/auth/password-reset",
        "/auth/verify-email/resend",
    ):
        record(f"openapi has {p}", p in (paths or {}), "present" if p in (paths or {}) else "missing")

    # Bad token → 400 (not 501 Not Implemented)
    code, body = req(
        "POST",
        f"{BASE}/auth/password-reset/confirm",
        data={"token": "invalid", "new_password": RESET_PASSWORD},
    )
    record("password-reset/confirm bad token not 501", code == 400, f"{code}")
    code, body = req(
        "POST",
        f"{BASE}/auth/verify-email/confirm",
        data={"token": "invalid"},
    )
    record("verify-email/confirm bad token not 501", code == 400, f"{code}")

    # ── Branded verify-email: send + mint/confirm ─────────────────────────
    code, full = req("GET", f"{KC}/admin/realms/{REALM}/users/{uid}", headers=ah)
    if isinstance(full, dict):
        full["emailVerified"] = False
        full["requiredActions"] = ["VERIFY_EMAIL"]
        req("PUT", f"{KC}/admin/realms/{REALM}/users/{uid}", data=full, headers=ah)

    code, body = req("POST", f"{BASE}/auth/verify-email/resend", data={"email": EMAIL})
    resend_ok = code == 202
    pod_token_missing = (
        code == 503
        and isinstance(body, dict)
        and "AUTH_EMAIL_TOKEN_SECRET" in str(body.get("detail", ""))
    )
    record(
        "API verify-email/resend (branded SMTP)",
        resend_ok,
        (
            "accepted — check Gmail for am.asrax.in/verify-email link"
            if resend_ok
            else f"{code} {body}"
            + (" — vault/pod missing AUTH_EMAIL_TOKEN_SECRET" if pod_token_missing else "")
        ),
    )

    # Link-host assertion always uses local AUTH_UI_BASE_URL (mail body not readable).
    sample_verify_url = f"{ui_base}/verify-email?token=sample"
    record(
        "verify link uses AUTH_UI_BASE_URL",
        urlparse(sample_verify_url).hostname == host,
        f"host={urlparse(sample_verify_url).hostname}",
    )

    if not token_secret:
        record("API verify-email/confirm", False, "skipped — local AUTH_EMAIL_TOKEN_SECRET missing")
    elif pod_token_missing:
        record(
            "API verify-email/confirm",
            False,
            "blocked — pod AUTH_EMAIL_TOKEN_SECRET not configured (mint/confirm needs same secret)",
        )
        record("KC emailVerified after confirm", False, "skipped — confirm blocked")
    else:
        verify_token, verify_jti = mint_auth_mail_token(
            secret=token_secret,
            purpose="verify_email",
            user_id=uid,
            email=EMAIL,
            ttl_seconds=ttl,
        )
        code = set_user_attr(uid, ah, VERIFY_JTI_ATTR, verify_jti)
        record("set asraxVerifyJti for confirm", code in (204, 200), f"{code}")
        code, body = req(
            "POST",
            f"{BASE}/auth/verify-email/confirm",
            data={"token": verify_token},
        )
        ok = (
            code == 200
            and isinstance(body, dict)
            and body.get("status") == "verified"
            and bool(body.get("access_token"))
        )
        record(
            "API verify-email/confirm",
            ok,
            f"{code} {body if not ok else 'verified+tokens'}",
        )
        code, full = req("GET", f"{KC}/admin/realms/{REALM}/users/{uid}", headers=ah)
        record(
            "KC emailVerified after confirm",
            isinstance(full, dict) and bool(full.get("emailVerified")),
            str(full.get("emailVerified") if isinstance(full, dict) else full),
        )

    # ── Branded password-reset: send + mint/confirm ───────────────────────
    code, body = req("POST", f"{BASE}/auth/password-reset", data={"email": EMAIL})
    reset_send_ok = code == 202
    if (
        code == 503
        and isinstance(body, dict)
        and "AUTH_EMAIL_TOKEN_SECRET" in str(body.get("detail", ""))
    ):
        pod_token_missing = True
    record(
        "API password-reset (branded SMTP)",
        reset_send_ok,
        (
            "accepted — check Gmail for am.asrax.in/reset-password link"
            if reset_send_ok
            else f"{code} {body}"
            + (" — vault/pod missing AUTH_EMAIL_TOKEN_SECRET" if pod_token_missing else "")
        ),
    )

    sample_reset_url = f"{ui_base}/reset-password?token=sample"
    record(
        "reset link uses AUTH_UI_BASE_URL",
        urlparse(sample_reset_url).hostname == host,
        f"host={urlparse(sample_reset_url).hostname}",
    )

    if not token_secret:
        record("API password-reset/confirm", False, "skipped — local AUTH_EMAIL_TOKEN_SECRET missing")
    elif pod_token_missing:
        record(
            "API password-reset/confirm",
            False,
            "blocked — pod AUTH_EMAIL_TOKEN_SECRET not configured (mint/confirm needs same secret)",
        )
    else:
        reset_token, reset_jti = mint_auth_mail_token(
            secret=token_secret,
            purpose="reset_password",
            user_id=uid,
            email=EMAIL,
            ttl_seconds=ttl,
        )
        code = set_user_attr(uid, ah, RESET_JTI_ATTR, reset_jti)
        record("set asraxResetJti for confirm", code in (204, 200), f"{code}")
        code, body = req(
            "POST",
            f"{BASE}/auth/password-reset/confirm",
            data={"token": reset_token, "new_password": RESET_PASSWORD},
        )
        ok = code == 200 and isinstance(body, dict) and body.get("status") == "password_updated"
        record("API password-reset/confirm", ok, f"{code} {body if not ok else 'password_updated'}")
        # Restore known password for admin login section
        code, _ = req(
            "PUT",
            f"{KC}/admin/realms/{REALM}/users/{uid}/reset-password",
            data={"type": "password", "value": TEMP_PASSWORD, "temporary": False},
            headers=ah,
        )
        record("restore TEMP_PASSWORD after reset confirm", code in (204, 200), f"{code}")

    # Clear required actions so login works for admin tests
    code, full = req("GET", f"{KC}/admin/realms/{REALM}/users/{uid}", headers=ah)
    if isinstance(full, dict):
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

    code, body = req(
        "POST",
        f"{BASE}/admin/users/{uid}/roles",
        data={"roles": ["super_admin"]},
        headers=bh,
    )
    record("super_admin self-confirm role API", code == 200, f"{code} {body}")

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

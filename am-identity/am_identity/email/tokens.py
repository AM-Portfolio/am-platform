from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any, Literal

Purpose = Literal["verify_email", "reset_password"]


class AuthMailTokenError(Exception):
    """Invalid, expired, or mismatched auth mail token."""


def _b64encode(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return urlsafe_b64decode(raw + padding)


def mint_auth_mail_token(
    *,
    secret: str,
    purpose: Purpose,
    user_id: str,
    email: str,
    ttl_seconds: int,
) -> tuple[str, str]:
    """Return (token, jti). Token is HMAC-signed payload (not a JWT library dependency)."""
    if not secret:
        raise AuthMailTokenError("AUTH_EMAIL_TOKEN_SECRET is not configured")
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


def verify_auth_mail_token(
    token: str,
    *,
    secret: str,
    expected_purpose: Purpose,
) -> dict[str, Any]:
    if not secret:
        raise AuthMailTokenError("AUTH_EMAIL_TOKEN_SECRET is not configured")
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise AuthMailTokenError("Malformed token") from exc
    expected = _b64encode(
        hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()
    )
    if not hmac.compare_digest(expected, sig):
        raise AuthMailTokenError("Invalid token signature")
    try:
        payload = json.loads(_b64decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthMailTokenError("Malformed token payload") from exc
    if payload.get("purpose") != expected_purpose:
        raise AuthMailTokenError("Token purpose mismatch")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise AuthMailTokenError("Token expired")
    if not payload.get("sub") or not payload.get("jti") or not payload.get("email"):
        raise AuthMailTokenError("Token missing claims")
    return payload

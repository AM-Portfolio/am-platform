"""Phase 1 referral capture + Kafka event helpers."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from am_identity.core import kafka as kafka_mod
from am_identity.core.config import IdentitySettings
from am_identity.core.kafka import (
    EVENT_EMAIL_VERIFIED,
    EVENT_USER_REGISTERED,
    normalize_referral_code,
    publish_email_verified,
    publish_user_registered,
    signup_attribution_payload,
)
from am_identity.providers.keycloak_provider import KeycloakIdentityProvider
from am_identity.schemas.auth import GoogleTokenRequest, RegisterRequest


def _settings(**overrides: Any) -> IdentitySettings:
    base = {
        "KEYCLOAK_URL": "http://localhost/auth",
        "KEYCLOAK_REALM": "am-realm",
        "KEYCLOAK_ADMIN_USER": "admin",
        "KEYCLOAK_ADMIN_PASSWORD": "secret",
        "OIDC_TOKEN_URL": "http://localhost/auth/realms/am-realm/protocol/openid-connect/token",
        "OIDC_ISSUER": "http://localhost/auth/realms/am-realm",
        "OIDC_JWKS_URL": "http://localhost/auth/realms/am-realm/protocol/openid-connect/certs",
        "AM_IDENTITY_CLIENT_SECRET": "svc-secret",
        "GOOGLE_CLIENT_ID": "test-google-client",
        "ALLOWED_GOOGLE_REDIRECT_URIS": "http://localhost/callback",
        "AUTH_UI_BASE_URL": "http://localhost:9000",
        "KAFKA_ENABLED": "false",
        "APP_ENV": "test",
    }
    base.update(overrides)
    return IdentitySettings(**base)


def test_register_without_referral_fields() -> None:
    req = RegisterRequest(email="a@example.com", password="Password1")
    assert req.referral_code is None
    assert req.device_id is None


def test_register_with_garbage_referral_code_accepted() -> None:
    req = RegisterRequest(
        email="a@example.com",
        password="Password1",
        referral_code="not-a-real-code!!!",
        device_id="device-uuid-12345678",
    )
    assert req.referral_code == "not-a-real-code!!!"
    assert req.device_id == "device-uuid-12345678"


def test_register_strips_blank_referral() -> None:
    req = RegisterRequest(
        email="a@example.com",
        password="Password1",
        referral_code="   ",
        device_id="  ",
    )
    assert req.referral_code is None
    assert req.device_id is None


def test_google_token_request_accepts_attribution() -> None:
    req = GoogleTokenRequest(
        id_token="tok",
        referral_code=" ab12cd34 ",
        device_id="dev-1",
    )
    assert req.referral_code == "ab12cd34"
    assert req.device_id == "dev-1"


def test_normalize_referral_code_uppercases() -> None:
    assert normalize_referral_code(" ab12xy99 ") == "AB12XY99"
    assert normalize_referral_code(None) is None


def test_signup_payload_includes_code_when_provided() -> None:
    payload = signup_attribution_payload(
        user_id="u1",
        email="a@example.com",
        referral_code="zz99aa11",
        device_id="device-aaaaaaaa",
    )
    assert payload == {
        "user_id": "u1",
        "email": "a@example.com",
        "referral_code": "ZZ99AA11",
        "device_id": "device-aaaaaaaa",
    }


def test_signup_payload_omits_absent_optional_fields() -> None:
    payload = signup_attribution_payload(user_id="u1", email="a@example.com")
    assert "referral_code" not in payload
    assert "device_id" not in payload


@pytest.mark.asyncio
async def test_publish_user_registered_builds_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_publish(
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        captured["topic"] = topic
        captured["event_type"] = event_type
        captured["payload"] = payload
        captured["kwargs"] = kwargs

    monkeypatch.setattr(kafka_mod, "publish_event", fake_publish)
    monkeypatch.setattr(kafka_mod, "get_settings", lambda: _settings())

    await publish_user_registered(
        user_id="user-1",
        email="a@example.com",
        referral_code="code1234",
        device_id="device-bbbbbbbb",
    )
    assert captured["event_type"] == EVENT_USER_REGISTERED
    assert captured["payload"]["referral_code"] == "CODE1234"
    assert captured["kwargs"]["idempotency_key"] == "user-registered:user-1"


@pytest.mark.asyncio
async def test_publish_email_verified_repeats_referral_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_publish(
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        captured["event_type"] = event_type
        captured["payload"] = payload
        captured["kwargs"] = kwargs

    monkeypatch.setattr(kafka_mod, "publish_event", fake_publish)

    await publish_email_verified(
        user_id="user-1",
        email="a@example.com",
        referral_code="code1234",
        device_id="device-bbbbbbbb",
    )
    assert captured["event_type"] == EVENT_EMAIL_VERIFIED
    assert captured["payload"]["referral_code"] == "CODE1234"
    assert captured["payload"]["device_id"] == "device-bbbbbbbb"
    assert captured["kwargs"]["idempotency_key"] == "email-verified:user-1"


@pytest.mark.asyncio
async def test_email_verified_emitted_once_on_google_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = KeycloakIdentityProvider(_settings())
    published: list[str] = []

    async def fake_publish_email_verified(**kwargs: Any) -> None:
        published.append("email_verified")

    async def fake_publish_user_registered(**kwargs: Any) -> None:
        published.append("user_registered")

    users = {
        "u-new": {
            "id": "u-new",
            "email": "g@example.com",
            "attributes": {},
        }
    }

    async def fake_get_raw(user_id: str, admin_token: str | None = None) -> dict[str, Any]:
        return json.loads(json.dumps(users[user_id]))

    async def fake_set_attrs(user_id: str, updates: dict[str, str | None]) -> None:
        attrs = users[user_id].setdefault("attributes", {})
        for key, value in updates.items():
            if value is None:
                attrs.pop(key, None)
            else:
                attrs[key] = [value]

    monkeypatch.setattr(provider, "_get_admin_access_token", AsyncMock(return_value="t"))
    monkeypatch.setattr(provider, "_get_raw_user", fake_get_raw)
    monkeypatch.setattr(provider, "_set_user_attrs", fake_set_attrs)
    monkeypatch.setattr(
        "am_identity.providers.keycloak_provider.publish_email_verified",
        fake_publish_email_verified,
    )
    monkeypatch.setattr(
        "am_identity.providers.keycloak_provider.publish_user_registered",
        fake_publish_user_registered,
    )

    first = await provider._emit_email_verified_once(
        user_id="u-new",
        email="g@example.com",
        referral_code="ABCD1234",
        device_id="device-cccccccc",
    )
    second = await provider._emit_email_verified_once(
        user_id="u-new",
        email="g@example.com",
        referral_code="ABCD1234",
        device_id="device-cccccccc",
    )
    assert first is True
    assert second is False
    assert published.count("email_verified") == 1


@pytest.mark.asyncio
async def test_user_registered_not_emitted_twice_on_relogin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = KeycloakIdentityProvider(_settings())
    published: list[str] = []

    async def fake_publish_user_registered(**kwargs: Any) -> None:
        published.append("user_registered")

    users = {
        "u1": {"id": "u1", "email": "a@example.com", "attributes": {}},
    }

    async def fake_get_raw(user_id: str, admin_token: str | None = None) -> dict[str, Any]:
        return json.loads(json.dumps(users[user_id]))

    async def fake_set_attrs(user_id: str, updates: dict[str, str | None]) -> None:
        attrs = users[user_id].setdefault("attributes", {})
        for key, value in updates.items():
            if value is None:
                attrs.pop(key, None)
            else:
                attrs[key] = [value]

    monkeypatch.setattr(provider, "_get_admin_access_token", AsyncMock(return_value="t"))
    monkeypatch.setattr(provider, "_get_raw_user", fake_get_raw)
    monkeypatch.setattr(provider, "_set_user_attrs", fake_set_attrs)
    monkeypatch.setattr(
        "am_identity.providers.keycloak_provider.publish_user_registered",
        fake_publish_user_registered,
    )

    assert await provider._emit_user_registered(
        user_id="u1", email="a@example.com", referral_code=None, device_id=None
    )
    assert not await provider._emit_user_registered(
        user_id="u1", email="a@example.com", referral_code=None, device_id=None
    )
    assert published == ["user_registered"]


def test_password_policy_still_enforced() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@example.com", password="password")

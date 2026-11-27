"""Sign in with Apple token validation and Keycloak account handling."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWKClientConnectionError

from am_identity.core.config import IdentitySettings
from am_identity.providers.keycloak_provider import KeycloakIdentityProvider


@pytest.fixture
def apple_provider() -> tuple[KeycloakIdentityProvider, rsa.RSAPrivateKey]:
    settings = IdentitySettings(
        KEYCLOAK_URL="http://localhost",
        KEYCLOAK_REALM="am-realm",
        KEYCLOAK_ADMIN_USER="admin",
        KEYCLOAK_ADMIN_PASSWORD="secret",
        OIDC_TOKEN_URL="http://localhost/realms/am-realm/protocol/openid-connect/token",
        OIDC_ISSUER="http://localhost/realms/am-realm",
        OIDC_JWKS_URL="http://localhost/realms/am-realm/protocol/openid-connect/certs",
        AM_IDENTITY_CLIENT_SECRET="svc-secret",
        GOOGLE_CLIENT_ID="test-google-client",
        ALLOWED_GOOGLE_REDIRECT_URIS="http://localhost/callback",
        AUTH_UI_BASE_URL="http://localhost:9000",
        KAFKA_ENABLED="false",
        APP_ENV="test",
    )
    provider = KeycloakIdentityProvider(settings)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    provider._apple_jwk_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda _token: SimpleNamespace(
            key=private_key.public_key()
        )
    )
    provider._get_admin_access_token = AsyncMock(return_value="admin-token")
    provider._issue_tokens_for_user = AsyncMock(
        return_value={"access_token": "am-token"}
    )
    provider._emit_user_registered = AsyncMock()
    provider._emit_email_verified_once = AsyncMock()
    return provider, private_key


def _signed_token(private_key: rsa.RSAPrivateKey, **overrides: object) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://appleid.apple.com",
        "aud": "com.asrax.aminvestment",
        "sub": "apple-subject-1",
        "email": "user@privaterelay.appleid.com",
        "email_verified": "true",
        "iat": now,
        "exp": now + 600,
        **overrides,
    }
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"iss": "https://not-apple.example"},
        {"aud": "another.bundle.id"},
        {"exp": 1},
        {"email_verified": "false"},
        {"email": None},
    ],
)
async def test_apple_rejects_invalid_claims_before_keycloak(
    apple_provider: tuple[KeycloakIdentityProvider, rsa.RSAPrivateKey],
    override: dict[str, object],
) -> None:
    provider, private_key = apple_provider
    with pytest.raises(HTTPException) as exc:
        await provider.authenticate_apple_token(_signed_token(private_key, **override))
    assert exc.value.status_code == 401
    provider._get_admin_access_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_apple_rejects_invalid_signature(
    apple_provider: tuple[KeycloakIdentityProvider, rsa.RSAPrivateKey],
) -> None:
    provider, _ = apple_provider
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(HTTPException) as exc:
        await provider.authenticate_apple_token(_signed_token(other_key))
    assert exc.value.status_code == 401
    provider._get_admin_access_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_apple_reports_jwks_outage(
    apple_provider: tuple[KeycloakIdentityProvider, rsa.RSAPrivateKey],
) -> None:
    provider, private_key = apple_provider

    def unavailable(_token: str) -> None:
        raise PyJWKClientConnectionError("unavailable")

    provider._apple_jwk_client = SimpleNamespace(get_signing_key_from_jwt=unavailable)
    with pytest.raises(HTTPException) as exc:
        await provider.authenticate_apple_token(_signed_token(private_key))
    assert exc.value.status_code == 503
    provider._get_admin_access_token.assert_not_awaited()


def _mock_keycloak_users(
    monkeypatch: pytest.MonkeyPatch,
    initial_users: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    users = list(initial_users)
    creations: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            username = request.url.params.get("username")
            return httpx.Response(
                200, json=[u for u in users if u.get("username") == username]
            )
        if request.method == "POST":
            body = json.loads(request.content)
            creations.append(body)
            users.append({**body, "id": "new-user-id"})
            return httpx.Response(201)
        return httpx.Response(405)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **_kwargs: real_client(transport=httpx.MockTransport(handler)),
    )
    return users, creations


@pytest.mark.asyncio
async def test_apple_creates_user_then_issues_keycloak_tokens(
    apple_provider: tuple[KeycloakIdentityProvider, rsa.RSAPrivateKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, private_key = apple_provider
    _, creations = _mock_keycloak_users(monkeypatch, [])
    provider._find_user_by_email = AsyncMock(return_value=None)

    result = await provider.authenticate_apple_token(
        _signed_token(private_key), given_name="A", family_name="Tester"
    )

    assert result == {"access_token": "am-token"}
    assert len(creations) == 1
    assert creations[0]["username"] == "apple_apple-subject-1"
    assert creations[0]["email"] == "user@privaterelay.appleid.com"
    assert creations[0]["emailVerified"] is True
    provider._issue_tokens_for_user.assert_awaited_once_with("new-user-id")
    provider._emit_user_registered.assert_awaited_once()


@pytest.mark.asyncio
async def test_apple_returning_user_reuses_keycloak_account(
    apple_provider: tuple[KeycloakIdentityProvider, rsa.RSAPrivateKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, private_key = apple_provider
    _, creations = _mock_keycloak_users(
        monkeypatch,
        [{"id": "existing-apple-id", "username": "apple_apple-subject-1"}],
    )

    result = await provider.authenticate_apple_token(_signed_token(private_key))

    assert result == {"access_token": "am-token"}
    assert creations == []
    provider._issue_tokens_for_user.assert_awaited_once_with("existing-apple-id")
    provider._emit_user_registered.assert_not_awaited()


@pytest.mark.asyncio
async def test_apple_does_not_take_over_existing_email_account(
    apple_provider: tuple[KeycloakIdentityProvider, rsa.RSAPrivateKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, private_key = apple_provider
    _, creations = _mock_keycloak_users(monkeypatch, [])
    provider._find_user_by_email = AsyncMock(return_value={"id": "password-user"})

    with pytest.raises(HTTPException) as exc:
        await provider.authenticate_apple_token(_signed_token(private_key))

    assert exc.value.status_code == 409
    assert creations == []
    provider._issue_tokens_for_user.assert_not_awaited()

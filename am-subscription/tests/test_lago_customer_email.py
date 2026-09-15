"""Lago customer email create / update behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from am_subscription.core.config import SubscriptionSettings
from am_subscription.providers.lago_provider import LagoProvider


def _settings() -> SubscriptionSettings:
    return SubscriptionSettings(
        LAGO_API_URL="https://lago.test",
        LAGO_ORG_API_KEY="test-key",
        APP_ENV="test",
        AM_SUBSCRIPTION_DB_PASSWORD="",
    )


def _mock_response(status: int, payload: dict[str, Any] | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status
    response.text = ""
    response.content = b"{}" if payload is not None else b""
    response.json.return_value = payload or {}
    return response


@pytest.mark.asyncio
async def test_ensure_customer_creates_with_email() -> None:
    provider = LagoProvider(_settings())
    get_resp = _mock_response(404)
    post_resp = _mock_response(
        200,
        {"customer": {"external_id": "am-user-1", "email": "a@example.com"}},
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=get_resp)
    mock_client.request = AsyncMock(return_value=post_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "am_subscription.providers.lago_provider.httpx.AsyncClient",
        return_value=mock_client,
    ):
        customer = await provider.ensure_customer(
            "am-user-1", email="a@example.com"
        )

    assert customer["email"] == "a@example.com"
    assert mock_client.request.await_count == 1
    method, url = mock_client.request.await_args.args[:2]
    assert method == "POST"
    assert url.endswith("/api/v1/customers")
    body = mock_client.request.await_args.kwargs["json"]
    assert body["customer"]["email"] == "a@example.com"
    assert body["customer"]["name"] == "a@example.com"


@pytest.mark.asyncio
async def test_ensure_customer_updates_missing_email() -> None:
    provider = LagoProvider(_settings())
    get_resp = _mock_response(
        200,
        {"customer": {"external_id": "am-user-2", "email": None}},
    )
    post_resp = _mock_response(
        200,
        {"customer": {"external_id": "am-user-2", "email": "b@example.com"}},
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=get_resp)
    mock_client.request = AsyncMock(return_value=post_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "am_subscription.providers.lago_provider.httpx.AsyncClient",
        return_value=mock_client,
    ):
        customer = await provider.ensure_customer(
            "am-user-2", email="b@example.com"
        )

    assert customer["email"] == "b@example.com"
    method, url = mock_client.request.await_args.args[:2]
    assert method == "POST"
    assert url.endswith("/api/v1/customers")
    body = mock_client.request.await_args.kwargs["json"]
    assert body["customer"]["email"] == "b@example.com"


@pytest.mark.asyncio
async def test_ensure_customer_skips_update_when_email_matches() -> None:
    provider = LagoProvider(_settings())
    get_resp = _mock_response(
        200,
        {"customer": {"external_id": "am-user-3", "email": "C@Example.com"}},
    )

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=get_resp)
    mock_client.request = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "am_subscription.providers.lago_provider.httpx.AsyncClient",
        return_value=mock_client,
    ):
        customer = await provider.ensure_customer(
            "am-user-3", email="c@example.com"
        )

    assert customer["email"] == "C@Example.com"
    mock_client.request.assert_not_awaited()

from __future__ import annotations

import re
from typing import Any

import httpx
from am_platform_common import InternalServerError

from am_notification.core.config import NotificationSettings
from am_notification.core.log_utils import get_logger
from am_notification.providers.interface import INotificationProvider

logger = get_logger("novu_provider")


def _novu_trigger_name(workflow_key: str) -> str:
    """Novu trigger identifiers slugify dots/underscores to hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", workflow_key.lower()).strip("-")


class NovuProvider(INotificationProvider):
    def __init__(self, settings: NotificationSettings) -> None:
        self._settings = settings
        self._base_url = settings.novu_api_url.rstrip("/")
        self._headers = {
            "Authorization": f"ApiKey {settings.novu_api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200, 201),
    ) -> dict[str, Any]:
        if not self._settings.novu_api_key:
            raise InternalServerError(
                message="Novu API key is not configured",
                error_code="NOVU_NOT_CONFIGURED",
            )
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method, url, headers=self._headers, json=json, params=params
            )
        if response.status_code not in expected:
            logger.error(
                "Novu API error",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "response_preview": response.text[:300],
                },
            )
            raise InternalServerError(
                message="Notification provider request failed",
                error_code="NOVU_API_ERROR",
                details={"status_code": response.status_code, "path": path},
            )
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {"data": data}

    async def ensure_subscriber(
        self, user_id: str, *, email: str | None = None, locale: str = "en"
    ) -> None:
        payload: dict[str, Any] = {"subscriberId": user_id, "locale": locale}
        if email:
            payload["email"] = email
        await self._request("POST", "/v1/subscribers", json=payload, expected=(200, 201))

    async def trigger(
        self,
        *,
        workflow_key: str,
        user_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> str:
        body = {
            "name": _novu_trigger_name(workflow_key),
            "to": {"subscriberId": user_id},
            "payload": payload,
            "transactionId": idempotency_key,
        }
        result = await self._request("POST", "/v1/events/trigger", json=body)
        transaction_id = result.get("data", {}).get("transactionId") or idempotency_key
        return str(transaction_id)

    async def list_in_app(
        self, user_id: str, *, page: int, page_size: int, unread_only: bool
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "limit": page_size}
        if unread_only:
            params["read"] = False
        result = await self._request(
            "GET",
            f"/v1/subscribers/{user_id}/notifications/feed",
            params=params,
        )
        items = result.get("data", [])
        return items if isinstance(items, list) else []

    async def unread_count(self, user_id: str) -> int:
        result = await self._request("GET", f"/v1/subscribers/{user_id}/notifications/unseen")
        count = result.get("data", {}).get("count", 0)
        return int(count)

    async def mark_read(self, user_id: str, notification_ids: list[str]) -> None:
        for notification_id in notification_ids:
            await self._request(
                "POST",
                f"/v1/subscribers/{user_id}/messages/{notification_id}/read",
                expected=(200, 201, 204),
            )

    async def mark_all_read(self, user_id: str) -> None:
        await self._request(
            "POST",
            f"/v1/subscribers/{user_id}/messages/mark-as",
            json={"mark": {"read": True}},
            expected=(200, 201, 204),
        )

    async def health_check(self) -> bool:
        if not self._settings.novu_api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/notification-templates",
                    headers=self._headers,
                    params={"page": 0, "limit": 1},
                )
            return response.status_code < 500
        except Exception:
            return False

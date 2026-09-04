from __future__ import annotations

from typing import Any

import httpx
from am_platform_common import InternalServerError, NotFoundError

from am_subscription.core.config import SubscriptionSettings
from am_subscription.core.log_utils import get_logger
from am_subscription.providers.interface import IMeteringProvider, ISubscriptionProvider

logger = get_logger("lago_provider")


class LagoProvider(ISubscriptionProvider, IMeteringProvider):
    def __init__(self, settings: SubscriptionSettings) -> None:
        self._settings = settings
        self._base_url = settings.lago_api_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {settings.lago_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; AM-Subscription/1.0)",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        expected: tuple[int, ...] = (200, 201),
    ) -> dict[str, Any]:
        if not self._settings.lago_api_key:
            raise InternalServerError(
                message="Lago API key is not configured",
                error_code="LAGO_NOT_CONFIGURED",
            )
        url = f"{self._base_url}{path}"
        logger.debug("Lago request", extra={"method": method, "path": path})
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method, url, headers=self._headers, json=json
            )
        if response.status_code not in expected:
            body_preview = response.text[:500] if response.text else ""
            logger.error(
                "Lago API error",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "response_preview": body_preview,
                },
            )
            raise InternalServerError(
                message="Billing provider request failed",
                error_code="LAGO_API_ERROR",
                details={"status_code": response.status_code, "path": path},
            )
        if not response.content:
            return {}
        return response.json()

    async def list_plans(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v1/plans?per_page=100")
        return payload.get("plans", [])

    async def ensure_customer(
        self,
        external_customer_id: str,
        email: str | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self._base_url}/api/v1/customers/{external_customer_id}",
                headers=self._headers,
            )
        if response.status_code == 200:
            payload = response.json()
            return payload.get("customer", payload)

        body: dict[str, Any] = {
            "customer": {
                "external_id": external_customer_id,
                "name": external_customer_id,
            }
        }
        if email:
            body["customer"]["email"] = email
        payload = await self._request("POST", "/api/v1/customers", json=body)
        return payload.get("customer", payload)

    async def create_subscription(
        self,
        external_customer_id: str,
        plan_code: str,
        *,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        subscription_body: dict[str, Any] = {
            "external_customer_id": external_customer_id,
            "plan_code": plan_code,
            "billing_time": "anniversary",
        }
        if external_id:
            subscription_body["external_id"] = external_id
        payload = await self._request(
            "POST",
            "/api/v1/subscriptions",
            json={"subscription": subscription_body},
        )
        return payload.get("subscription", payload)

    async def cancel_subscription(
        self, external_subscription_id: str
    ) -> dict[str, Any]:
        payload = await self._request(
            "DELETE",
            f"/api/v1/subscriptions/{external_subscription_id}",
            expected=(200,),
        )
        return payload.get("subscription", payload)

    async def change_plan(
        self, external_subscription_id: str, plan_code: str
    ) -> dict[str, Any]:
        payload = await self._request(
            "PUT",
            f"/api/v1/subscriptions/{external_subscription_id}",
            json={"subscription": {"plan_code": plan_code}},
        )
        return payload.get("subscription", payload)

    async def send_usage_event(
        self,
        external_customer_id: str,
        metric_code: str,
        quantity: int,
        *,
        transaction_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "transaction_id": transaction_id,
            "external_customer_id": external_customer_id,
            "code": metric_code,
            "properties": properties or {"quantity": quantity},
        }
        if metric_code == "portfolios":
            event["properties"] = {"active_count": quantity, **(properties or {})}
        await self._request("POST", "/api/v1/events", json={"event": event})

    async def get_plan(self, plan_code: str) -> dict[str, Any]:
        try:
            payload = await self._request("GET", f"/api/v1/plans/{plan_code}")
        except InternalServerError as exc:
            if exc.details.get("status_code") == 404:
                raise NotFoundError(message=f"Plan not found: {plan_code}") from exc
            raise
        return payload.get("plan", payload)

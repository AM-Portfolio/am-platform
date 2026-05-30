from abc import ABC, abstractmethod
from typing import Any


class ISubscriptionProvider(ABC):
    @abstractmethod
    async def list_plans(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def ensure_customer(self, external_customer_id: str, email: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def create_subscription(
        self,
        external_customer_id: str,
        plan_code: str,
        *,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def cancel_subscription(self, external_subscription_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def change_plan(self, external_subscription_id: str, plan_code: str) -> dict[str, Any]:
        raise NotImplementedError


class IMeteringProvider(ABC):
    @abstractmethod
    async def send_usage_event(
        self,
        external_customer_id: str,
        metric_code: str,
        quantity: int,
        *,
        transaction_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError

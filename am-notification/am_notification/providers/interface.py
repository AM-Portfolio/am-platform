from abc import ABC, abstractmethod
from typing import Any


class INotificationProvider(ABC):
    @abstractmethod
    async def ensure_subscriber(
        self, user_id: str, *, email: str | None = None, locale: str = "en"
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def trigger(
        self,
        *,
        workflow_key: str,
        user_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def list_in_app(
        self, user_id: str, *, page: int, page_size: int, unread_only: bool
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def unread_count(self, user_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    async def mark_read(self, user_id: str, notification_ids: list[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    async def mark_all_read(self, user_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

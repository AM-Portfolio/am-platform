from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from am_identity.schemas.auth import RegisterRequest


class IIdentityProvider(ABC):
    @abstractmethod
    async def create_user(self, payload: RegisterRequest) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def authenticate_otp(self, username: str, otp: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def revoke_token(self, refresh_token: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_current_user_info(self, access_token: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_user_settings(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def update_user_settings(self, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def issue_service_token(self, audience: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def build_google_auth_url(self, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def authenticate_google(self, code: str, state: str, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError

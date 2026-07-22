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
    async def update_user_settings(
        self, user_id: str, settings: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def issue_service_token(self, audience: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def build_google_auth_url(self, redirect_uri: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def authenticate_google(
        self, code: str, state: str, redirect_uri: str
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def authenticate_google_token(self, id_token: str) -> dict[str, Any]:
        raise NotImplementedError

    # ── Admin / email helpers ───────────────────────────────────────────────

    @abstractmethod
    async def list_users(
        self,
        *,
        email: str | None = None,
        search: str | None = None,
        first: int = 0,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_user(self, user_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def create_admin_user(
        self,
        *,
        email: str,
        password: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        enabled: bool = True,
        send_verify_email: bool = True,
        temporary_password: bool = False,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def update_user(
        self,
        user_id: str,
        *,
        enabled: bool | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def set_user_enabled(self, user_id: str, enabled: bool) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def list_realm_roles(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    async def get_user_realm_roles(self, user_id: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def set_user_realm_roles(
        self, user_id: str, role_names: list[str]
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def add_user_realm_roles(
        self, user_id: str, role_names: list[str]
    ) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def remove_user_realm_role(self, user_id: str, role_name: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    async def execute_actions_email(
        self,
        user_id: str,
        actions: list[str],
        *,
        lifespan_seconds: int | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_verify_email(self, user_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send_password_reset_email(self, email: str) -> bool:
        """Return True if a user was found and mail was triggered; False if unknown email."""
        raise NotImplementedError

    @abstractmethod
    async def confirm_verify_email(
        self, token: str | None = None, code: str | None = None
    ) -> dict[str, Any]:
        """Mark email verified, clear VERIFY_EMAIL required actions, return OIDC tokens."""
        raise NotImplementedError

    @abstractmethod
    async def confirm_password_reset(
        self,
        new_password: str,
        token: str | None = None,
        code: str | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def change_password(
        self, *, username: str, current_password: str, new_password: str
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def logout_user_sessions(self, user_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def set_user_attribute(
        self, user_id: str, key: str, value: str
    ) -> dict[str, Any]:
        """Set or update a single custom attribute for a user."""
        raise NotImplementedError

    @abstractmethod
    async def set_user_attributes(
        self, user_id: str, attributes: dict[str, Any]
    ) -> dict[str, Any]:
        """Update multiple user custom attributes in a single Keycloak API transaction."""
        raise NotImplementedError

    @abstractmethod
    async def remove_user_attribute(self, user_id: str, key: str) -> dict[str, Any]:
        """Remove a single custom attribute from a user."""
        raise NotImplementedError

    @abstractmethod
    async def hard_delete_user(self, user_id: str) -> None:
        """Permanently delete a user account from the identity provider."""
        raise NotImplementedError

    @abstractmethod
    async def is_user_deletion_pending(self, user_id: str) -> bool:
        """Check if user account has pending deletion state."""
        raise NotImplementedError

    @abstractmethod
    async def restore_user_account(self, user_id: str) -> bool:
        """Restore user account by clearing deletion attributes. Returns True if restored."""
        raise NotImplementedError

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from am_platform_security.config import SecuritySettings, get_security_settings
from am_platform_security.models import AuthContext
from am_platform_security.validator import TokenValidator

_bearer = HTTPBearer(auto_error=False)


@lru_cache(maxsize=1)
def get_token_validator() -> TokenValidator:
    settings = get_security_settings()
    return TokenValidator(settings)


def _extract_bearer_token(credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
        )
    return credentials.credentials


def require_auth_context(
    expected_audience: str | None = None,
    require_service_token: bool = False,
):
    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        validator: TokenValidator = Depends(get_token_validator),
    ) -> AuthContext:
        token = _extract_bearer_token(credentials)
        return validator.validate(
            token,
            expected_audience=expected_audience,
            require_service_token=require_service_token,
        )

    return dependency


def require_roles(required_roles: Iterable[str], expected_audience: str | None = None):
    required_roles_set = set(required_roles)

    def dependency(
        context: AuthContext = Depends(require_auth_context(expected_audience=expected_audience)),
    ) -> AuthContext:
        if not required_roles_set.issubset(set(context.roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required roles: {sorted(required_roles_set)}",
            )
        return context

    return dependency


def require_any_roles(allowed_roles: Iterable[str], expected_audience: str | None = None):
    """Caller must have at least one of the listed roles (OR semantics)."""
    allowed_roles_set = set(allowed_roles)

    def dependency(
        context: AuthContext = Depends(require_auth_context(expected_audience=expected_audience)),
    ) -> AuthContext:
        if not allowed_roles_set.intersection(set(context.roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {sorted(allowed_roles_set)}",
            )
        return context

    return dependency


def require_service_account(
    allowed_client_ids: Iterable[str] | None = None,
    expected_audience: str | None = None,
):
    allowed = set(allowed_client_ids or [])

    def dependency(
        context: AuthContext = Depends(
            require_auth_context(
                expected_audience=expected_audience,
                require_service_token=True,
            )
        ),
        settings: SecuritySettings = Depends(get_security_settings),
    ) -> AuthContext:
        if settings.service_role_name not in context.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing service role",
            )
        if allowed and (context.client_id not in allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Client is not allowed: {context.client_id}",
            )
        return context

    return dependency

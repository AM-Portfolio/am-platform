from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from am_platform_security.config import SecuritySettings, get_security_settings
from am_platform_security.models import AuthContext
from am_platform_security.validator import TokenValidator

_bearer = HTTPBearer(auto_error=False)

_LOCAL_DEV_SUBJECT = "local-dev-user"
_LOCAL_DEV_CLIENT_ID = "local-dev-client"


@lru_cache(maxsize=1)
def get_token_validator() -> TokenValidator:
    settings = get_security_settings()
    return TokenValidator(settings)


def _dev_auth_context(access_token: str = "local-dev-token") -> AuthContext:
    return AuthContext(
        subject=_LOCAL_DEV_SUBJECT,
        client_id=_LOCAL_DEV_CLIENT_ID,
        token_type="service",
        roles=["user", "service"],
        scopes=[],
        claims={"sub": _LOCAL_DEV_SUBJECT},
        access_token=access_token,
    )


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
        settings: SecuritySettings = Depends(get_security_settings),
    ) -> AuthContext:
        if settings.auth_disabled:
            token = credentials.credentials if credentials else "local-dev-token"
            return _dev_auth_context(token)

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
        if settings.auth_disabled:
            return context

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

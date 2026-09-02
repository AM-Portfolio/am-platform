from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from am_identity.services.cookie_utils import read_session_cookie
from am_platform_security import AuthContext
from am_platform_security.dependencies import get_token_validator

_bearer = HTTPBearer(auto_error=False)

_PLACEHOLDER_BEARER_TOKENS = frozenset({"bff_cookie_session"})


def _is_jwt_candidate(token: str) -> bool:
    return token.count(".") >= 2


def require_user_context():
    def dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        am_session: str | None = Cookie(default=None),
    ) -> AuthContext:
        if credentials is not None and credentials.scheme.lower() == "bearer":
            token = credentials.credentials
            if (
                token
                and token not in _PLACEHOLDER_BEARER_TOKENS
                and _is_jwt_candidate(token)
            ):
                validator = get_token_validator()
                return validator.validate(token)

        session = read_session_cookie(am_session)
        if session is not None:
            user = session.user
            return AuthContext(
                subject=user.sub,
                access_token=session.access_token,
                claims={
                    "sub": user.sub,
                    "email": user.email,
                    "preferred_username": user.preferred_username,
                    "given_name": user.given_name,
                    "family_name": user.family_name,
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return dependency

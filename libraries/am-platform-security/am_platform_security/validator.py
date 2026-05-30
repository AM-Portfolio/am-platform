from __future__ import annotations

from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientConnectionError

from am_platform_security.config import SecuritySettings
from am_platform_security.models import AuthContext

# Keycloak JWKS is behind a WAF that blocks default urllib User-Agent (403).
_JWKS_REQUEST_HEADERS = {
    "User-Agent": "am-platform-security/1.0",
    "Accept": "application/json",
}


def _realm_roles_from_claims(claims: dict[str, Any]) -> list[str]:
    top_level = claims.get("roles")
    if isinstance(top_level, list) and top_level:
        return [str(role) for role in top_level]
    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles")
        if isinstance(realm_roles, list):
            return [str(role) for role in realm_roles]
    return []


def _normalize_issuer(url: str) -> str:
    """Compare issuers ignoring http/https scheme (Keycloak frontends vary)."""
    return url.replace("https://", "http://", 1)


def _issuer_matches(token_issuer: str | None, configured_issuer: str) -> bool:
    if not token_issuer:
        return False
    if token_issuer == configured_issuer:
        return True
    return _normalize_issuer(token_issuer) == _normalize_issuer(configured_issuer)


class TokenValidator:
    def __init__(self, settings: SecuritySettings):
        self.settings = settings
        self._jwk_client = PyJWKClient(
            settings.oidc_jwks_url,
            headers=_JWKS_REQUEST_HEADERS,
            cache_jwk_set=True,
            lifespan=300,
        )

    def validate(
        self,
        token: str,
        *,
        expected_audience: str | None = None,
        require_service_token: bool = False,
    ) -> AuthContext:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token).key
            decode_kwargs: dict[str, Any] = {
                "algorithms": ["RS256"],
                "options": {
                    "verify_aud": expected_audience is not None,
                    "verify_iss": False,
                },
            }
            if expected_audience is not None:
                decode_kwargs["audience"] = expected_audience

            claims = jwt.decode(token, signing_key, **decode_kwargs)
            if not _issuer_matches(claims.get("iss"), self.settings.oidc_issuer):
                raise InvalidTokenError(
                    f"Invalid issuer (token={claims.get('iss')!r}, "
                    f"expected={self.settings.oidc_issuer!r})"
                )
        except PyJWKClientConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Unable to fetch JWKS signing keys: {exc}",
            ) from exc
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid access token: {exc}",
            ) from exc

        client_id = claims.get("azp") or claims.get("client_id")
        scopes = str(claims.get("scope", "")).split()
        roles = _realm_roles_from_claims(claims)
        token_type = claims.get("token_type")
        if not token_type:
            token_type = "service" if client_id and self.settings.service_role_name in roles else "user"

        if require_service_token and token_type != "service":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Service token required",
            )

        return AuthContext(
            subject=claims.get("sub", ""),
            client_id=client_id,
            token_type=token_type,
            roles=roles,
            scopes=scopes,
            claims=claims,
            access_token=token,
        )

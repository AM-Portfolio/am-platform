from __future__ import annotations

import ast
import json
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientConnectionError

from am_identity.core.config import IdentitySettings
from am_identity.providers.interface import IIdentityProvider
from am_identity.schemas.auth import RegisterRequest

# Required for /userinfo and OIDC profile claims (without openid, userinfo returns 403).
_OIDC_USER_SCOPES = "openid profile email"
_GOOGLE_ISSUER = "https://accounts.google.com"
_GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_JWKS_REQUEST_HEADERS = {
    "User-Agent": "am-identity-service/1.0",
    "Accept": "application/json",
}


def _parse_settings_attribute(attributes: dict[str, Any] | None) -> dict[str, Any]:
    """Read user settings stored in Keycloak multivalued `settings` attribute."""
    if not attributes:
        return {}
    raw = attributes.get("settings")
    if not raw:
        return {}
    value: Any = raw[0] if isinstance(raw, list) and raw else raw
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    try:
        parsed = ast.literal_eval(value)
        return parsed if isinstance(parsed, dict) else {}
    except (SyntaxError, ValueError):
        return {}


class KeycloakIdentityProvider(IIdentityProvider):
    def __init__(self, settings: IdentitySettings):
        self.settings = settings
        keycloak_base = settings.keycloak_url.rstrip("/")
        self._openid_base = (
            f"{keycloak_base}/realms/{settings.keycloak_realm}/protocol/openid-connect"
        )
        # Master-realm token endpoint (admin-cli); not the am-realm OIDC_TOKEN_URL.
        self._admin_token_url = (
            f"{keycloak_base}/realms/master/protocol/openid-connect/token"
        )
        self._admin_users_url = (
            f"{keycloak_base}/admin/realms/{settings.keycloak_realm}/users"
        )
        self._admin_roles_url = (
            f"{keycloak_base}/admin/realms/{settings.keycloak_realm}/roles"
        )
        self._auth_url = f"{self._openid_base}/auth"
        self._session_timeout = 20.0
        self._http_headers = {
            "User-Agent": "am-identity-service/1.0",
            "Accept": "application/json",
        }
        self._google_states: dict[str, tuple[str, float]] = {}
        self._allowed_redirect_uris = {
            uri.strip()
            for uri in settings.allowed_google_redirect_uris.split(",")
            if uri.strip()
        }
        self._settings_profile_ready = False
        self._user_profile_url = (
            f"{keycloak_base}/admin/realms/{settings.keycloak_realm}/users/profile"
        )
        self._google_jwk_client = PyJWKClient(
            _GOOGLE_JWKS_URL,
            headers=_JWKS_REQUEST_HEADERS,
            cache_jwk_set=True,
            lifespan=300,
        )

    def _validate_google_id_token(self, id_token: str) -> dict[str, Any]:
        try:
            signing_key = self._google_jwk_client.get_signing_key_from_jwt(id_token).key
            claims = jwt.decode(
                id_token,
                signing_key,
                algorithms=["RS256"],
                audience=self.settings.google_client_id,
                issuer=_GOOGLE_ISSUER,
            )
        except PyJWKClientConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Unable to fetch Google JWKS signing keys: {exc}",
            ) from exc
        except InvalidTokenError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid Google ID token: {exc}",
            ) from exc

        email = claims.get("email")
        if not email or not claims.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google account email is missing or not verified",
            )
        return claims

    async def _find_user_by_email(self, email: str, admin_token: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(
                self._admin_users_url,
                params={"email": email, "exact": "true"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to search Keycloak users: {response.text}",
            )
        users = response.json()
        return users[0] if users else None

    async def _ensure_google_user(self, claims: dict[str, Any]) -> str:
        email = str(claims["email"])
        google_sub = str(claims["sub"])
        admin_token = await self._get_admin_access_token()
        existing = await self._find_user_by_email(email, admin_token)
        if existing is None:
            payload = {
                "username": email,
                "email": email,
                "enabled": True,
                "emailVerified": True,
                "firstName": claims.get("given_name") or claims.get("name") or email,
                "lastName": claims.get("family_name") or "",
            }
            async with httpx.AsyncClient(
                timeout=self._session_timeout, verify=self.settings.verify_ssl
            ) as client:
                response = await client.post(
                    self._admin_users_url,
                    json=payload,
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
            if response.status_code not in (201, 204):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to provision Google user: {response.text}",
                )
            existing = await self._find_user_by_email(email, admin_token)
            if existing is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Google user was created but could not be loaded from Keycloak",
                )

        user_id = existing["id"]
        federated_url = (
            f"{self._admin_users_url}/{user_id}/federated-identity/"
            f"{self.settings.google_idp_alias}"
        )
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            link_response = await client.post(
                federated_url,
                json={
                    "identityProvider": self.settings.google_idp_alias,
                    "userId": google_sub,
                    "userName": email,
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        if link_response.status_code >= 400 and link_response.status_code != 409:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to link Google identity: {link_response.text}",
            )
        return user_id

    async def _issue_tokens_for_user(self, user_id: str) -> dict[str, Any]:
        return await self._request_token(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_id": self.settings.identity_client_id,
                "client_secret": self.settings.identity_client_secret,
                "requested_subject": user_id,
                "scope": _OIDC_USER_SCOPES,
            }
        )

    async def _request_token(self, data: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.post(self.settings.oidc_token_url, data=data)
        if response.status_code >= 400:
            body = response.text
            if "unauthorized_client" in body and "direct access" in body.lower():
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=(
                        f"Client '{data.get('client_id')}' cannot use password login. "
                        "Enable direct access grants on am-identity-service in Keycloak "
                        "(npm run infra:tf:apply). Keycloak response: "
                        f"{body}"
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token request failed: {body}",
            )
        return response.json()

    async def _get_admin_access_token(self) -> str:
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.post(
                self._admin_token_url,
                data={
                    "grant_type": "password",
                    "client_id": "admin-cli",
                    "username": self.settings.keycloak_admin_user,
                    "password": self.settings.keycloak_admin_password,
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Keycloak master admin login failed. "
                    "Check KEYCLOAK_ADMIN_USER and KEYCLOAK_ADMIN_PASSWORD "
                    f"(token URL: {self._admin_token_url}). "
                    f"Keycloak response: {response.text}"
                ),
            )
        return response.json()["access_token"]

    async def create_user(self, payload: RegisterRequest) -> dict[str, Any]:
        admin_token = await self._get_admin_access_token()
        req = {
            "username": payload.email,
            "email": payload.email,
            "enabled": True,
            "emailVerified": False,
            "firstName": payload.first_name,
            "lastName": payload.last_name,
            "credentials": [
                {"type": "password", "value": payload.password, "temporary": False}
            ],
        }
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.post(
                self._admin_users_url,
                json=req,
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        if response.status_code not in (201, 204):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Create user failed: {response.text}",
            )
        user_id = None
        location = response.headers.get("Location") or response.headers.get("location")
        if location and "/" in location:
            user_id = location.rstrip("/").split("/")[-1]
        if not user_id:
            found = await self._find_user_by_email(payload.email, admin_token)
            user_id = found.get("id") if found else None
        if user_id:
            try:
                await self.execute_actions_email(user_id, ["VERIFY_EMAIL"])
            except HTTPException:
                # User is created; mail failure should not undo registration.
                pass
        return {"status": "created", "email": payload.email, "id": user_id}

    async def authenticate(self, username: str, password: str) -> dict[str, Any]:
        return await self._request_token(
            {
                "grant_type": "password",
                "client_id": self.settings.identity_client_id,
                "client_secret": self.settings.identity_client_secret,
                "username": username,
                "password": password,
                "scope": _OIDC_USER_SCOPES,
            }
        )

    async def authenticate_otp(self, username: str, otp: str) -> dict[str, Any]:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="OTP login route is scaffolded but provider flow is not implemented yet.",
        )

    async def refresh_token(self, refresh_token: str) -> dict[str, Any]:
        return await self._request_token(
            {
                "grant_type": "refresh_token",
                "client_id": self.settings.identity_client_id,
                "client_secret": self.settings.identity_client_secret,
                "refresh_token": refresh_token,
                "scope": _OIDC_USER_SCOPES,
            }
        )

    async def revoke_token(self, refresh_token: str) -> None:
        logout_url = f"{self._openid_base}/logout"
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.post(
                logout_url,
                data={
                    "client_id": self.settings.identity_client_id,
                    "client_secret": self.settings.identity_client_secret,
                    "refresh_token": refresh_token,
                },
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Logout failed: {response.text}",
            )

    async def get_current_user_info(self, access_token: str) -> dict[str, Any]:
        url = f"{self._openid_base}/userinfo"
        headers = {**self._http_headers, "Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(url, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=(
                    f"User info failed (HTTP {response.status_code}): "
                    f"{response.text or 'empty body'}. "
                    "Log in again so the access token includes the openid scope."
                ),
            )
        user_info = response.json()
        user_info["roles"] = user_info.get("roles", [])
        return user_info

    async def _ensure_settings_profile_attribute(self) -> None:
        """Register `settings` on the realm user profile (Keycloak drops unknown attrs otherwise)."""
        if self._settings_profile_ready:
            return
        admin_token = await self._get_admin_access_token()
        headers = {**self._http_headers, "Authorization": f"Bearer {admin_token}"}
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(self._user_profile_url, headers=headers)
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to load realm user profile: {response.text}",
            )
        profile = response.json()
        names = {attr.get("name") for attr in profile.get("attributes", [])}
        if "settings" not in names:
            profile.setdefault("attributes", []).append(
                {
                    "name": "settings",
                    "displayName": "User Settings",
                    "multivalued": False,
                    "group": "user-metadata",
                    "permissions": {
                        "view": ["admin", "user"],
                        "edit": ["admin", "user"],
                    },
                }
            )
            async with httpx.AsyncClient(
                timeout=self._session_timeout, verify=self.settings.verify_ssl
            ) as client:
                put_response = await client.put(
                    self._user_profile_url,
                    json=profile,
                    headers=headers,
                )
            if put_response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Failed to register settings user profile attribute: {put_response.text}",
                )
        self._settings_profile_ready = True

    async def get_user_settings(self, user_id: str) -> dict[str, Any]:
        await self._ensure_settings_profile_attribute()
        admin_token = await self._get_admin_access_token()
        user_url = f"{self._admin_users_url}/{user_id}"
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(
                user_url,
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {user_id}",
            )
        return _parse_settings_attribute(response.json().get("attributes"))

    async def update_user_settings(
        self, user_id: str, settings: dict[str, Any]
    ) -> dict[str, Any]:
        await self._ensure_settings_profile_attribute()
        admin_token = await self._get_admin_access_token()
        user_url = f"{self._admin_users_url}/{user_id}"
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            get_response = await client.get(
                user_url, headers={"Authorization": f"Bearer {admin_token}"}
            )
            if get_response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User not found: {user_id}",
                )
            user = get_response.json()
            attrs = user.get("attributes") or {}
            attrs["settings"] = [json.dumps(settings)]
            user["attributes"] = attrs
            put_response = await client.put(
                user_url,
                json=user,
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        if put_response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Update settings failed: {put_response.text}",
            )
        saved = await self.get_user_settings(user_id)
        if not saved:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    "Settings were not persisted in Keycloak. "
                    "Ensure realm user profile includes the `settings` attribute "
                    "(npm run infra:tf:apply)."
                ),
            )
        return {"sub": user_id, "settings": saved}

    async def issue_service_token(self, audience: str | None = None) -> dict[str, Any]:
        data = {
            "grant_type": "client_credentials",
            "client_id": self.settings.identity_client_id,
            "client_secret": self.settings.identity_client_secret,
        }
        if audience:
            data["audience"] = audience
        return await self._request_token(data)

    def _validate_redirect_uri(self, redirect_uri: str) -> None:
        if redirect_uri not in self._allowed_redirect_uris:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Redirect URI is not allowed: {redirect_uri}",
            )

    def _cleanup_expired_states(self) -> None:
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._google_states.items() if exp <= now]
        for key in expired_keys:
            self._google_states.pop(key, None)

    async def build_google_auth_url(self, redirect_uri: str) -> dict[str, Any]:
        self._validate_redirect_uri(redirect_uri)
        self._cleanup_expired_states()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        expires_at = time.time() + self.settings.google_state_ttl_seconds
        self._google_states[state] = (nonce, expires_at)
        query = {
            "client_id": self.settings.web_client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "kc_idp_hint": self.settings.google_idp_alias,
        }
        return {
            "auth_url": f"{self._auth_url}?{urlencode(query)}",
            "state": state,
            "expires_in": self.settings.google_state_ttl_seconds,
        }

    async def authenticate_google(
        self, code: str, state: str, redirect_uri: str
    ) -> dict[str, Any]:
        self._validate_redirect_uri(redirect_uri)
        self._cleanup_expired_states()
        state_entry = self._google_states.pop(state, None)
        if state_entry is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired Google auth state",
            )
        token_data = {
            "grant_type": "authorization_code",
            "client_id": self.settings.web_client_id,
            "code": code,
            "redirect_uri": redirect_uri,
        }
        return await self._request_token(token_data)

    async def authenticate_google_token(self, id_token: str) -> dict[str, Any]:
        # Keycloak 26.3 cannot exchange Google id_tokens directly (Standard TE V2
        # rejects JWT; legacy external exchange fails for Google id_tokens). Validate
        # the Google token here, provision/link the user, then issue realm tokens via
        # direct impersonation (legacy token exchange without subject_token).
        claims = self._validate_google_id_token(id_token)
        user_id = await self._ensure_google_user(claims)
        return await self._issue_tokens_for_user(user_id)

    # ── Admin / email helpers ───────────────────────────────────────────────

    def _admin_headers(self, admin_token: str) -> dict[str, str]:
        return {**self._http_headers, "Authorization": f"Bearer {admin_token}"}

    def _normalize_user(self, user: dict[str, Any], roles: list[str] | None = None) -> dict[str, Any]:
        return {
            "id": user.get("id", ""),
            "email": user.get("email"),
            "username": user.get("username"),
            "first_name": user.get("firstName"),
            "last_name": user.get("lastName"),
            "enabled": bool(user.get("enabled", True)),
            "email_verified": bool(user.get("emailVerified", False)),
            "roles": roles if roles is not None else [],
        }

    async def list_users(
        self,
        *,
        email: str | None = None,
        search: str | None = None,
        first: int = 0,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        admin_token = await self._get_admin_access_token()
        params: dict[str, Any] = {"first": first, "max": max_results}
        if email:
            params["email"] = email
            params["exact"] = "true"
        elif search:
            params["search"] = search
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(
                self._admin_users_url,
                params=params,
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"List users failed: {response.text}",
            )
        users = response.json() or []
        result: list[dict[str, Any]] = []
        for user in users:
            uid = user.get("id")
            roles = await self.get_user_realm_roles(uid) if uid else []
            result.append(self._normalize_user(user, roles))
        return result

    async def get_user(self, user_id: str) -> dict[str, Any]:
        admin_token = await self._get_admin_access_token()
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(
                f"{self._admin_users_url}/{user_id}",
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User not found: {user_id}",
            )
        user = response.json()
        roles = await self.get_user_realm_roles(user_id)
        return self._normalize_user(user, roles)

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
        admin_token = await self._get_admin_access_token()
        req: dict[str, Any] = {
            "username": email,
            "email": email,
            "enabled": enabled,
            "emailVerified": False,
            "firstName": first_name,
            "lastName": last_name,
        }
        if password:
            req["credentials"] = [
                {
                    "type": "password",
                    "value": password,
                    "temporary": temporary_password,
                }
            ]
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.post(
                self._admin_users_url,
                json=req,
                headers=self._admin_headers(admin_token),
            )
        if response.status_code not in (201, 204):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Create user failed: {response.text}",
            )
        location = response.headers.get("Location") or response.headers.get("location")
        user_id = location.rstrip("/").split("/")[-1] if location else None
        if not user_id:
            found = await self._find_user_by_email(email, admin_token)
            user_id = found.get("id") if found else None
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User created but id could not be resolved",
            )
        actions: list[str] = []
        if send_verify_email:
            actions.append("VERIFY_EMAIL")
        if temporary_password or not password:
            actions.append("UPDATE_PASSWORD")
        if actions:
            await self.execute_actions_email(user_id, actions)
        return await self.get_user(user_id)

    async def update_user(
        self,
        user_id: str,
        *,
        enabled: bool | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        admin_token = await self._get_admin_access_token()
        headers = self._admin_headers(admin_token)
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            get_response = await client.get(
                f"{self._admin_users_url}/{user_id}", headers=headers
            )
            if get_response.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User not found: {user_id}",
                )
            user = get_response.json()
            if enabled is not None:
                user["enabled"] = enabled
            if first_name is not None:
                user["firstName"] = first_name
            if last_name is not None:
                user["lastName"] = last_name
            if attributes is not None:
                merged = user.get("attributes") or {}
                merged.update(attributes)
                user["attributes"] = merged
            put_response = await client.put(
                f"{self._admin_users_url}/{user_id}",
                json=user,
                headers=headers,
            )
        if put_response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Update user failed: {put_response.text}",
            )
        return await self.get_user(user_id)

    async def set_user_enabled(self, user_id: str, enabled: bool) -> dict[str, Any]:
        return await self.update_user(user_id, enabled=enabled)

    async def list_realm_roles(self) -> list[dict[str, Any]]:
        admin_token = await self._get_admin_access_token()
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(
                self._admin_roles_url,
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"List roles failed: {response.text}",
            )
        return response.json() or []

    async def _resolve_role_reps(self, role_names: list[str]) -> list[dict[str, Any]]:
        admin_token = await self._get_admin_access_token()
        reps: list[dict[str, Any]] = []
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            for name in role_names:
                response = await client.get(
                    f"{self._admin_roles_url}/{name}",
                    headers=self._admin_headers(admin_token),
                )
                if response.status_code >= 400:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unknown realm role: {name}",
                    )
                reps.append(response.json())
        return reps

    async def get_user_realm_roles(self, user_id: str) -> list[str]:
        admin_token = await self._get_admin_access_token()
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.get(
                f"{self._admin_users_url}/{user_id}/role-mappings/realm",
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Get user roles failed: {response.text}",
            )
        return [r.get("name") for r in (response.json() or []) if r.get("name")]

    async def set_user_realm_roles(self, user_id: str, role_names: list[str]) -> list[str]:
        current = await self.get_user_realm_roles(user_id)
        # Preserve non-human / system roles we do not manage via this API surface
        preserve = [r for r in current if r == "service" or r.startswith("default-roles-")]
        desired = list(dict.fromkeys([*preserve, *role_names]))
        to_add = [r for r in desired if r not in current]
        to_remove = [r for r in current if r not in desired]
        if to_add:
            await self.add_user_realm_roles(user_id, to_add)
        if to_remove:
            for name in to_remove:
                await self.remove_user_realm_role(user_id, name)
        return await self.get_user_realm_roles(user_id)

    async def add_user_realm_roles(self, user_id: str, role_names: list[str]) -> list[str]:
        if not role_names:
            return await self.get_user_realm_roles(user_id)
        admin_token = await self._get_admin_access_token()
        reps = await self._resolve_role_reps(role_names)
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.post(
                f"{self._admin_users_url}/{user_id}/role-mappings/realm",
                json=reps,
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Add roles failed: {response.text}",
            )
        return await self.get_user_realm_roles(user_id)

    async def remove_user_realm_role(self, user_id: str, role_name: str) -> list[str]:
        admin_token = await self._get_admin_access_token()
        reps = await self._resolve_role_reps([role_name])
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.request(
                "DELETE",
                f"{self._admin_users_url}/{user_id}/role-mappings/realm",
                json=reps,
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Remove role failed: {response.text}",
            )
        return await self.get_user_realm_roles(user_id)

    async def execute_actions_email(
        self,
        user_id: str,
        actions: list[str],
        *,
        lifespan_seconds: int | None = None,
    ) -> None:
        admin_token = await self._get_admin_access_token()
        params: dict[str, Any] = {}
        if lifespan_seconds is not None:
            params["lifespan"] = lifespan_seconds
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.put(
                f"{self._admin_users_url}/{user_id}/execute-actions-email",
                params=params,
                json=actions,
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Execute actions email failed: {response.text}",
            )

    async def send_verify_email(self, user_id: str) -> None:
        await self.execute_actions_email(user_id, ["VERIFY_EMAIL"])

    async def send_password_reset_email(self, email: str) -> bool:
        admin_token = await self._get_admin_access_token()
        user = await self._find_user_by_email(email, admin_token)
        if not user or not user.get("id"):
            return False
        await self.execute_actions_email(user["id"], ["UPDATE_PASSWORD"])
        return True

    async def logout_user_sessions(self, user_id: str) -> None:
        admin_token = await self._get_admin_access_token()
        async with httpx.AsyncClient(
            timeout=self._session_timeout, verify=self.settings.verify_ssl
        ) as client:
            response = await client.post(
                f"{self._admin_users_url}/{user_id}/logout",
                headers=self._admin_headers(admin_token),
            )
        if response.status_code >= 400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Logout user sessions failed: {response.text}",
            )

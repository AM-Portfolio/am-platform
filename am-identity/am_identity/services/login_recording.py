from __future__ import annotations

from typing import Any

from fastapi import Request

from am_identity.email.rate_limit import client_ip
from am_identity.services.geo_resolution import geo_from_request
from am_identity.services.login_session_service import ClientType, LoginContext, login_session_service
from am_identity.services.user_agent import parse_os_family
from am_platform_security.dependencies import get_token_validator


def _client_type(platform: str | None) -> ClientType:
    if platform in ("web", "android", "ios"):
        return platform
    return "web"


def _parse_browser(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    if "Edg/" in user_agent:
        return "Edge"
    if "Chrome/" in user_agent:
        return "Chrome"
    if "Firefox/" in user_agent:
        return "Firefox"
    if "Safari/" in user_agent:
        return "Safari"
    return None


def record_token_login(
    request: Request,
    tokens: dict[str, Any],
    *,
    platform: str | None = None,
) -> None:
    access_token = tokens.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        return
    try:
        context = get_token_validator().validate(access_token)
    except Exception:
        return
    user_agent = request.headers.get("user-agent")
    refresh_token = tokens.get("refresh_token")
    sid = context.claims.get("sid")
    geo = geo_from_request(request)
    login_session_service.record_login(
        LoginContext(
            user_id=context.subject,
            email=context.claims.get("email") if isinstance(context.claims.get("email"), str) else None,
            client_type=_client_type(platform),
            browser=_parse_browser(user_agent),
            os=parse_os_family(user_agent),
            ip=client_ip(request),
            user_agent=user_agent,
            machine_trust_key=request.headers.get("x-machine-trust-key"),
            access_token=access_token,
            refresh_token=refresh_token if isinstance(refresh_token, str) else None,
            keycloak_session_id=sid if isinstance(sid, str) else None,
            geo_city=geo.city,
            geo_country=geo.country,
        )
    )

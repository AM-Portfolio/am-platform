from __future__ import annotations

from typing import Any

from am_identity.providers.interface import IIdentityProvider


async def issue_web_session_tokens(
    provider: IIdentityProvider,
    user_id: str,
) -> tuple[str, str | None, int | None]:
    issue = getattr(provider, "issue_user_session_tokens", None)
    if issue is None:
        return f"web-access-{user_id}", f"web-refresh-{user_id}", None

    payload: dict[str, Any] = await issue(user_id)
    return (
        payload["access_token"],
        payload.get("refresh_token"),
        payload.get("expires_in"),
    )

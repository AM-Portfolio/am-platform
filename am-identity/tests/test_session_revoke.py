from __future__ import annotations

import pytest
from fastapi import HTTPException

from am_identity.services.login_session_service import LoginContext, LoginSessionService


def _record(service: LoginSessionService, *, browser: str, machine_key: str) -> str:
    result = service.record_login(
        LoginContext(
            user_id="user-1",
            email="user@example.com",
            client_type="web",
            browser=browser,
            os="Windows",
            ip="203.0.113.10",
            user_agent="Mozilla/5.0",
            machine_trust_key=machine_key,
        )
    )
    return result.login_session.session_id


def test_revoke_one_leaves_other_sessions() -> None:
    service = LoginSessionService()
    chrome = _record(service, browser="Chrome", machine_key="machine-a")
    firefox = _record(service, browser="Firefox", machine_key="machine-b")
    service.revoke_login_session("user-1", chrome)
    active = service.list_login_sessions("user-1")
    active_ids = {session.session_id for session in active}
    assert chrome not in active_ids
    assert firefox in active_ids


def test_revoke_all_clears_sessions() -> None:
    service = LoginSessionService()
    _record(service, browser="Chrome", machine_key="machine-a")
    _record(service, browser="Firefox", machine_key="machine-b")
    count = service.revoke_all_login_sessions("user-1")
    assert count == 2
    assert service.list_login_sessions("user-1") == ()


def test_revoke_unknown_session_raises_404() -> None:
    service = LoginSessionService()
    with pytest.raises(HTTPException) as exc:
        service.revoke_login_session("user-1", "missing")
    assert exc.value.status_code == 404

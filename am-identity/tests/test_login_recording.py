from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import Request

from am_identity.services.login_recording import record_token_login
from am_identity.services.login_session_service import login_session_service
from am_platform_security.models import AuthContext


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    login_session_service._known_devices.clear()
    login_session_service._login_sessions.clear()
    login_session_service._security_events.clear()


def test_record_token_login_creates_session(monkeypatch: pytest.MonkeyPatch) -> None:
    validator = MagicMock()
    validator.validate.return_value = AuthContext(
        subject="user-email-login",
        client_id="am-web",
        token_type="user",
        roles=[],
        scopes=[],
        claims={"sub": "user-email-login", "email": "user@example.com", "sid": "kc-sid-1"},
        access_token="access-token",
    )
    monkeypatch.setattr(
        "am_identity.services.login_recording.get_token_validator",
        lambda: validator,
    )

    scope = {"type": "http", "headers": [], "client": ("127.0.0.1", 0)}
    request = Request(scope)

    record_token_login(
        request,
        {"access_token": "access-token", "refresh_token": "refresh-token"},
        platform="web",
    )

    sessions = login_session_service.list_login_sessions("user-email-login")
    assert len(sessions) == 1
    assert sessions[0].keycloak_session_id == "kc-sid-1"
    assert sessions[0].client_type == "web"

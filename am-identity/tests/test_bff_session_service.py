from __future__ import annotations

from am_identity.services.bff_session_service import BffSessionService, BffUser, bff_session_service
from am_identity.services.cookie_utils import read_session_cookie, set_session_cookie


class _Response:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}
        self.cookie_options: dict[str, dict[str, object]] = {}

    def set_cookie(self, key: str, value: str, **kwargs: object) -> None:
        self.cookies[key] = value
        self.cookie_options[key] = kwargs


def test_create_session_and_read_cookie() -> None:
    user = BffUser(sub="user-1", email="user@example.com", preferred_username="user@example.com")
    session = bff_session_service.create_session(
        user=user,
        access_token="access-token",
        refresh_token="refresh-token",
    )
    loaded = read_session_cookie(session.session_id)
    assert loaded is not None
    assert loaded.user.sub == "user-1"
    assert loaded.access_token == "access-token"


def test_set_cookie_uses_http_only_am_session() -> None:
    service = BffSessionService()
    user = BffUser(sub="user-1", email="user@example.com")
    session = service.create_session(user=user, access_token="access", refresh_token=None)
    response = _Response()

    class _Settings:
        app_env = "dev"

    set_session_cookie(response, session, _Settings())  # type: ignore[arg-type]
    assert response.cookies["am_session"] == session.session_id
    assert response.cookie_options["am_session"]["httponly"] is True
    assert response.cookie_options["am_session"]["samesite"] == "lax"


def test_audit_log_records_events() -> None:
    service = BffSessionService()
    service.append_audit(event="poll_success", session_id="sess-1", user_id="user-1", ip="1.2.3.4")
    entries = service.list_audit()
    assert len(entries) == 1
    assert entries[0].event == "poll_success"

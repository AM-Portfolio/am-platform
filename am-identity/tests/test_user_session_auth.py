from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from am_identity.main import app
from am_identity.services.bff_session_service import BffUser, bff_session_service


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_login_sessions_accepts_bff_cookie(client: TestClient) -> None:
    session = bff_session_service.create_session(
        user=BffUser(sub="user-cookie", email="cookie@example.com"),
        access_token="web-access-user-cookie",
        refresh_token="web-refresh-user-cookie",
    )
    client.cookies.set("am_session", session.session_id)

    response = client.get("/users/me/login-sessions")
    assert response.status_code == 200
    assert response.json() == []

"""C0.52 — 401 without service token on internal routes."""

from __future__ import annotations

import uuid

from am_user_platform.main import app
from am_user_platform.modules.ai.api.internal_router import ServiceAuth
from am_user_platform.modules.ai.api.session_router import UserAuth
from tests.conftest import service_context, user_context


def test_internal_append_requires_auth(client) -> None:
    app.dependency_overrides.clear()
    session_id = uuid.uuid4()
    response = client.post(
        f"/internal/ai/sessions/{session_id}/messages",
        json={
            "user_id": "user-1",
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "messages": [{"role": "user", "content": "Hi"}],
        },
    )
    assert response.status_code == 401
    app.dependency_overrides[ServiceAuth] = service_context
    app.dependency_overrides[UserAuth] = lambda: user_context("api-test-user")


def test_internal_context_requires_auth(client) -> None:
    app.dependency_overrides.clear()
    session_id = uuid.uuid4()
    response = client.get(
        f"/internal/ai/sessions/{session_id}/context",
        params={"user_id": "user-1", "limit": 5},
    )
    assert response.status_code == 401
    app.dependency_overrides[ServiceAuth] = service_context
    app.dependency_overrides[UserAuth] = lambda: user_context("api-test-user")


def test_internal_purge_requires_auth(client) -> None:
    app.dependency_overrides.clear()
    response = client.delete("/internal/ai/users/user-1/data")
    assert response.status_code == 401
    app.dependency_overrides[ServiceAuth] = service_context
    app.dependency_overrides[UserAuth] = lambda: user_context("api-test-user")

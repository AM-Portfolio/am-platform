"""HTTP API tests for ai routers."""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient

from am_platform_security import AuthContext

from am_user_platform.core.database import init_db, ping_db
from am_user_platform.main import app
from am_user_platform.modules.ai.api.internal_router import ServiceAuth
from am_user_platform.modules.ai.api.session_router import UserAuth


def _service_context() -> AuthContext:
    return AuthContext(
        subject="am-fin-agent",
        client_id="am-fin-agent",
        token_type="service",
        roles=["service"],
        access_token="test-service-token",
    )


def _user_context(user_id: str) -> AuthContext:
    return AuthContext(
        subject=user_id,
        client_id="am-app",
        token_type="user",
        roles=["user"],
        access_token="test-user-token",
    )


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def auth_overrides():
    app.dependency_overrides[ServiceAuth] = _service_context
    app.dependency_overrides[UserAuth] = lambda: _user_context("api-test-user")
    yield
    app.dependency_overrides.clear()


def test_internal_append_requires_auth_when_override_cleared(client: TestClient) -> None:
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
    app.dependency_overrides[ServiceAuth] = _service_context
    app.dependency_overrides[UserAuth] = lambda: _user_context("api-test-user")


def test_internal_routes_registered(client: TestClient) -> None:
    assert any(r.path.startswith("/internal/ai") for r in app.routes)


def test_user_routes_registered(client: TestClient) -> None:
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/v1/user-platform/ai/sessions" in paths
    assert "/v1/user-platform/ai/feedback" in paths


@pytest.fixture(scope="module")
def postgres_ready() -> bool:
    if not asyncio.run(ping_db()):
        return False
    asyncio.run(init_db())
    return True


def test_internal_append_and_context_integration(
    client: TestClient, postgres_ready: bool
) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    user_id = f"api-user-{uuid.uuid4()}"
    session_id = uuid.uuid4()
    append = client.post(
        f"/internal/ai/sessions/{session_id}/messages",
        json={
            "user_id": user_id,
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "messages": [
                {"role": "user", "content": "Portfolio summary?"},
                {
                    "role": "assistant",
                    "content": "Here you go",
                    "tokens_used": 900,
                },
            ],
        },
    )
    assert append.status_code == 201
    assert len(append.json()["data"]) == 2

    context = client.get(
        f"/internal/ai/sessions/{session_id}/context",
        params={"user_id": user_id, "limit": 10},
    )
    assert context.status_code == 200
    assert len(context.json()["data"]["messages"]) == 2

    purge = client.delete(f"/internal/ai/users/{user_id}/data")
    assert purge.status_code == 200
    assert purge.json()["data"]["sessions_deleted"] >= 1


def test_user_session_tenancy(client: TestClient, postgres_ready: bool) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    owner_id = f"owner-{uuid.uuid4()}"
    other_id = f"other-{uuid.uuid4()}"
    session_id = uuid.uuid4()

    app.dependency_overrides[ServiceAuth] = _service_context
    created = client.post(
        f"/internal/ai/sessions/{session_id}/messages",
        json={
            "user_id": owner_id,
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert created.status_code == 201

    app.dependency_overrides[UserAuth] = lambda: _user_context(other_id)
    denied = client.get(f"/v1/user-platform/ai/sessions/{session_id}")
    assert denied.status_code == 404

    app.dependency_overrides[ServiceAuth] = _service_context
    client.delete(f"/internal/ai/users/{owner_id}/data")


def test_user_feedback_integration(client: TestClient, postgres_ready: bool) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    user_id = f"fb-user-{uuid.uuid4()}"
    session_id = uuid.uuid4()

    app.dependency_overrides[ServiceAuth] = _service_context
    client.post(
        f"/internal/ai/sessions/{session_id}/messages",
        json={
            "user_id": user_id,
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "messages": [
                {"role": "user", "content": "Q"},
                {"role": "assistant", "content": "A"},
            ],
        },
    )

    app.dependency_overrides[UserAuth] = lambda: _user_context(user_id)
    feedback = client.post(
        "/v1/user-platform/ai/feedback",
        json={
            "session_id": str(session_id),
            "agent_type": "fin_portfolio",
            "rating": "down",
            "comment": "Not helpful",
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["data"]["rating"] == "down"

    app.dependency_overrides[ServiceAuth] = _service_context
    client.delete(f"/internal/ai/users/{user_id}/data")

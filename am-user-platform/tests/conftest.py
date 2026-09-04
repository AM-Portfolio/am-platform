"""Shared fixtures for am-user-platform tests."""

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


def service_context() -> AuthContext:
    return AuthContext(
        subject="am-fin-agent",
        client_id="am-fin-agent",
        token_type="service",
        roles=["service"],
        access_token="test-service-token",
    )


def user_context(user_id: str) -> AuthContext:
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


@pytest.fixture
def api_user_id() -> str:
    return "api-test-user"


@pytest.fixture(autouse=True)
def auth_overrides(api_user_id: str):
    app.dependency_overrides[ServiceAuth] = service_context
    app.dependency_overrides[UserAuth] = lambda: user_context(api_user_id)
    yield
    app.dependency_overrides.clear()


@pytest.fixture(scope="session")
def postgres_ready() -> bool:
    if not asyncio.run(ping_db()):
        return False
    asyncio.run(init_db())
    return True


@pytest.fixture
def user_id() -> str:
    return f"test-user-{uuid.uuid4()}"


@pytest.fixture
def other_user_id() -> str:
    return f"test-user-{uuid.uuid4()}"

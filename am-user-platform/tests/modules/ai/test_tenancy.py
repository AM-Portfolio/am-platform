"""C0.51 — user A cannot read/delete user B session."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from am_platform_common import NotFoundError

from am_user_platform.core.database import get_session_factory
from am_user_platform.main import app
from am_user_platform.modules.ai.api.session_router import UserAuth
from am_user_platform.modules.ai.schemas.session import SessionCreate
from am_user_platform.modules.ai.services.session_service import SessionService
from tests.conftest import user_context


def _run(coro):
    return asyncio.run(coro)


def test_tenancy_get_and_delete_session(
    postgres_ready: bool, user_id: str, other_user_id: str
) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    async def _test() -> None:
        factory = get_session_factory()
        async with factory() as db:
            sessions = SessionService(db)
            created = await sessions.create_session(
                user_id,
                SessionCreate(
                    product_id="am_app",
                    agent_type="fin_portfolio",
                ),
            )
            with pytest.raises(NotFoundError):
                await sessions.get_session(created.id, other_user_id)
            with pytest.raises(NotFoundError):
                await sessions.soft_delete(created.id, other_user_id)

            still = await sessions.get_session(created.id, user_id)
            assert still.id == created.id

            listed = await sessions.list_sessions(other_user_id)
            assert all(item.id != created.id for item in listed.items)

            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())


def test_user_api_tenancy(client, postgres_ready: bool) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    owner_id = f"owner-{uuid.uuid4()}"
    other_id = f"other-{uuid.uuid4()}"
    session_id = uuid.uuid4()

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

    app.dependency_overrides[UserAuth] = lambda: user_context(other_id)
    denied = client.get(f"/v1/user-platform/ai/sessions/{session_id}")
    assert denied.status_code == 404

    deleted = client.delete(f"/v1/user-platform/ai/sessions/{session_id}")
    assert deleted.status_code == 404

    app.dependency_overrides[UserAuth] = lambda: user_context(owner_id)
    owned = client.get(f"/v1/user-platform/ai/sessions/{session_id}")
    assert owned.status_code == 200

    client.delete(f"/internal/ai/users/{owner_id}/data")

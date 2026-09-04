"""C0.48 — create, list, update title, soft delete."""

from __future__ import annotations

import asyncio

import pytest

from am_platform_common import NotFoundError

from am_user_platform.core.database import get_session_factory
from am_user_platform.modules.ai.schemas.session import SessionCreate
from am_user_platform.modules.ai.services.session_service import SessionService


def _run(coro):
    return asyncio.run(coro)


def test_create_list_update_soft_delete(
    postgres_ready: bool, user_id: str
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
                    title="First chat",
                ),
            )
            assert created.title == "First chat"
            assert created.user_id == user_id

            listed = await sessions.list_sessions(
                user_id, product_id="am_app", agent_type="fin_portfolio"
            )
            assert listed.total >= 1
            assert any(item.id == created.id for item in listed.items)

            renamed = await sessions.update_title(
                created.id, user_id, "Renamed chat"
            )
            assert renamed.title == "Renamed chat"

            await sessions.soft_delete(created.id, user_id)
            with pytest.raises(NotFoundError):
                await sessions.get_session(created.id, user_id)

            after = await sessions.list_sessions(user_id)
            assert all(item.id != created.id for item in after.items)

            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())


def test_create_session_via_user_api(
    client, postgres_ready: bool, api_user_id: str
) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    created = client.post(
        "/v1/user-platform/ai/sessions",
        json={
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "title": "API session",
        },
    )
    assert created.status_code == 201
    session_id = created.json()["data"]["id"]

    listed = client.get(
        "/v1/user-platform/ai/sessions",
        params={"product_id": "am_app", "agent_type": "fin_portfolio"},
    )
    assert listed.status_code == 200
    assert any(item["id"] == session_id for item in listed.json()["data"]["items"])

    patched = client.patch(
        f"/v1/user-platform/ai/sessions/{session_id}",
        json={"title": "Patched"},
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["title"] == "Patched"

    deleted = client.delete(f"/v1/user-platform/ai/sessions/{session_id}")
    assert deleted.status_code == 204

    from am_user_platform.main import app
    from am_user_platform.modules.ai.api.internal_router import ServiceAuth
    from tests.conftest import service_context

    app.dependency_overrides[ServiceAuth] = service_context
    client.delete(f"/internal/ai/users/{api_user_id}/data")

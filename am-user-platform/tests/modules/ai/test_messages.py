"""C0.49 — append, get context, tokens_used stored."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from am_user_platform.core.database import get_session_factory
from am_user_platform.modules.ai.models.db import MessageRole
from am_user_platform.modules.ai.schemas.message import (
    AppendMessagesRequest,
    MessageAppendItem,
)
from am_user_platform.modules.ai.schemas.session import SessionCreate
from am_user_platform.modules.ai.services.message_service import MessageService
from am_user_platform.modules.ai.services.session_service import SessionService


def _run(coro):
    return asyncio.run(coro)


def test_append_get_context_tokens_used(postgres_ready: bool, user_id: str) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    async def _test() -> None:
        factory = get_session_factory()
        async with factory() as db:
            sessions = SessionService(db)
            messages = MessageService(db)
            session_id = uuid.uuid4()
            await sessions.create_session(
                user_id,
                SessionCreate(
                    id=session_id,
                    product_id="am_app",
                    agent_type="fin_portfolio",
                ),
            )
            await messages.append_messages(
                session_id,
                AppendMessagesRequest(
                    user_id=user_id,
                    product_id="am_app",
                    agent_type="fin_portfolio",
                    messages=[
                        MessageAppendItem(role=MessageRole.user, content="Portfolio?"),
                        MessageAppendItem(
                            role=MessageRole.assistant,
                            content="Summary",
                            tokens_used=1200,
                            tools_used=["get_portfolio_summary"],
                        ),
                    ],
                ),
            )
            ctx = await messages.get_context(session_id, user_id, limit=5)
            assert len(ctx.messages) == 2
            assert ctx.messages[0].role == MessageRole.user
            assert ctx.messages[1].tokens_used == 1200
            assert ctx.messages[1].tools_used == ["get_portfolio_summary"]

            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())


def test_internal_append_and_context_api(client, postgres_ready: bool) -> None:
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
    assert append.json()["data"][1]["tokens_used"] == 900

    context = client.get(
        f"/internal/ai/sessions/{session_id}/context",
        params={"user_id": user_id, "limit": 10},
    )
    assert context.status_code == 200
    assert len(context.json()["data"]["messages"]) == 2

    client.delete(f"/internal/ai/users/{user_id}/data")

"""C0.50 — create feedback linked to session/message."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from am_user_platform.core.database import get_session_factory
from am_user_platform.modules.ai.models.db import MessageRole
from am_user_platform.modules.ai.schemas.feedback import FeedbackCreate
from am_user_platform.modules.ai.schemas.message import (
    AppendMessagesRequest,
    MessageAppendItem,
)
from am_user_platform.modules.ai.schemas.session import SessionCreate
from am_user_platform.modules.ai.services.feedback_service import FeedbackService
from am_user_platform.modules.ai.services.message_service import MessageService
from am_user_platform.modules.ai.services.session_service import SessionService
from am_user_platform.main import app
from am_user_platform.modules.ai.api.session_router import UserAuth
from tests.conftest import user_context


def _run(coro):
    return asyncio.run(coro)


def test_feedback_linked_to_session_and_message(
    postgres_ready: bool, user_id: str
) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    async def _test() -> None:
        factory = get_session_factory()
        async with factory() as db:
            sessions = SessionService(db)
            messages = MessageService(db)
            feedback = FeedbackService(db)
            created = await sessions.create_session(
                user_id,
                SessionCreate(
                    product_id="am_app",
                    agent_type="fin_portfolio",
                ),
            )
            rows = await messages.append_messages(
                created.id,
                AppendMessagesRequest(
                    user_id=user_id,
                    product_id="am_app",
                    agent_type="fin_portfolio",
                    messages=[
                        MessageAppendItem(role=MessageRole.user, content="Q"),
                        MessageAppendItem(role=MessageRole.assistant, content="A"),
                    ],
                ),
            )
            assistant_id = rows[-1].id
            row = await feedback.create_feedback(
                user_id,
                FeedbackCreate(
                    session_id=created.id,
                    message_id=assistant_id,
                    agent_type="fin_portfolio",
                    rating="up",
                    comment="helpful",
                ),
            )
            assert row.session_id == created.id
            assert row.message_id == assistant_id
            assert row.rating == "up"

            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())


def test_user_feedback_api(client, postgres_ready: bool) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    user_id = f"fb-user-{uuid.uuid4()}"
    session_id = uuid.uuid4()
    append = client.post(
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
    assert append.status_code == 201
    message_id = append.json()["data"][-1]["id"]

    app.dependency_overrides[UserAuth] = lambda: user_context(user_id)
    feedback = client.post(
        "/v1/user-platform/ai/feedback",
        json={
            "session_id": str(session_id),
            "message_id": message_id,
            "agent_type": "fin_portfolio",
            "rating": "down",
            "comment": "Not helpful",
        },
    )
    assert feedback.status_code == 201
    data = feedback.json()["data"]
    assert data["rating"] == "down"
    assert data["session_id"] == str(session_id)
    assert data["message_id"] == message_id

    client.delete(f"/internal/ai/users/{user_id}/data")

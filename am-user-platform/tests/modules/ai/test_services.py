"""Service integration tests — require Postgres (skip if unavailable)."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from am_platform_common import NotFoundError

from am_user_platform.core.database import get_session_factory, init_db, ping_db
from am_user_platform.modules.ai.models.db import MessageRole
from am_user_platform.modules.ai.schemas.feedback import FeedbackCreate
from am_user_platform.modules.ai.schemas.message import AppendMessagesRequest, MessageAppendItem
from am_user_platform.modules.ai.schemas.session import SessionCreate
from am_user_platform.modules.ai.services.message_service import MessageService
from am_user_platform.modules.ai.services.session_service import SessionService


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def postgres_ready() -> bool:
    if not _run(ping_db()):
        return False
    _run(init_db())
    return True


@pytest.fixture
def user_id() -> str:
    return f"test-user-{uuid.uuid4()}"


@pytest.fixture
def other_user_id() -> str:
    return f"test-user-{uuid.uuid4()}"


def test_session_list_scoped_to_user(
    postgres_ready: bool, user_id: str, other_user_id: str
) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    async def _test() -> None:
        factory = get_session_factory()
        async with factory() as db:
            sessions = SessionService(db)
            await sessions.create_session(
                user_id,
                SessionCreate(
                    product_id="am_app",
                    agent_type="fin_portfolio",
                ),
            )
            await sessions.create_session(
                other_user_id,
                SessionCreate(
                    product_id="am_app",
                    agent_type="fin_portfolio",
                ),
            )
            listed = await sessions.list_sessions(user_id)
            assert listed.total >= 1
            assert all(item.user_id == user_id for item in listed.items)
            await db.commit()
            await sessions.purge_user_data(user_id)
            await sessions.purge_user_data(other_user_id)
            await db.commit()

    _run(_test())


def test_append_messages_and_context(postgres_ready: bool, user_id: str) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    async def _test() -> None:
        factory = get_session_factory()
        async with factory() as db:
            sessions = SessionService(db)
            messages = MessageService(db)
            session_id = uuid.uuid4()
            created = await sessions.create_session(
                user_id,
                SessionCreate(
                    id=session_id,
                    product_id="am_app",
                    agent_type="fin_portfolio",
                ),
            )
            before_updated = created.updated_at

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
                            content="Here is your summary",
                            tokens_used=1200,
                        ),
                    ],
                ),
            )
            await db.flush()

            refreshed = await sessions.get_session(session_id, user_id)
            assert refreshed.updated_at >= before_updated
            assert refreshed.title == "Portfolio?"

            ctx = await messages.get_context(session_id, user_id, limit=5)
            assert len(ctx.messages) == 2
            assert ctx.messages[0].role == MessageRole.user
            assert ctx.messages[1].tokens_used == 1200

            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())


def test_get_context_returns_last_n_in_order(postgres_ready: bool, user_id: str) -> None:
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
            batch = AppendMessagesRequest(
                user_id=user_id,
                product_id="am_app",
                agent_type="fin_portfolio",
                messages=[
                    MessageAppendItem(role=MessageRole.user, content=f"msg-{i}")
                    for i in range(6)
                ],
            )
            await messages.append_messages(session_id, batch)

            ctx = await messages.get_context(session_id, user_id, limit=3)
            assert len(ctx.messages) == 3
            assert ctx.messages[0].content == "msg-3"
            assert ctx.messages[-1].content == "msg-5"

            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())


def test_tenancy_get_session(postgres_ready: bool, user_id: str, other_user_id: str) -> None:
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
            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())


def test_feedback_create(postgres_ready: bool, user_id: str) -> None:
    if not postgres_ready:
        pytest.skip("Postgres not available")

    async def _test() -> None:
        from am_user_platform.modules.ai.services.feedback_service import FeedbackService

        factory = get_session_factory()
        async with factory() as db:
            sessions = SessionService(db)
            feedback = FeedbackService(db)
            created = await sessions.create_session(
                user_id,
                SessionCreate(
                    product_id="am_app",
                    agent_type="fin_portfolio",
                ),
            )
            row = await feedback.create_feedback(
                user_id,
                FeedbackCreate(
                    session_id=created.id,
                    agent_type="fin_portfolio",
                    rating="up",
                ),
            )
            assert row.rating == "up"
            await db.commit()
            await sessions.purge_user_data(user_id)
            await db.commit()

    _run(_test())

"""Schema validation tests — no Postgres required."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from am_user_platform.modules.ai.models.db import MessageRole
from am_user_platform.modules.ai.schemas.feedback import FeedbackCreate, FeedbackResponse
from am_user_platform.modules.ai.schemas.message import (
    AppendMessagesRequest,
    ContextResponse,
    MessageAppendItem,
    MessageResponse,
)
from am_user_platform.modules.ai.schemas.session import (
    SessionCreate,
    SessionListResponse,
    SessionResponse,
    SessionUpdate,
)


def test_session_create_from_json() -> None:
    payload = SessionCreate.model_validate(
        {
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "channel": "user_app",
            "title": "My chat",
        }
    )
    assert payload.product_id == "am_app"


def test_session_update_from_json() -> None:
    payload = SessionUpdate.model_validate({"title": "Renamed"})
    assert payload.title == "Renamed"


def test_append_messages_request_from_json() -> None:
    payload = AppendMessagesRequest.model_validate(
        {
            "user_id": "user-1",
            "product_id": "am_app",
            "agent_type": "fin_portfolio",
            "messages": [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "Hi",
                    "tokens_used": 42,
                    "tools_used": ["get_portfolio_summary"],
                },
            ],
        }
    )
    assert len(payload.messages) == 2
    assert payload.messages[1].tokens_used == 42


def test_feedback_create_from_json() -> None:
    session_id = uuid.uuid4()
    payload = FeedbackCreate.model_validate(
        {
            "session_id": str(session_id),
            "agent_type": "fin_portfolio",
            "rating": "down",
            "comment": "Wrong numbers",
        }
    )
    assert payload.rating == "down"


def test_session_response_round_trip() -> None:
    now = datetime.now(timezone.utc)
    session_id = uuid.uuid4()
    dto = SessionResponse(
        id=session_id,
        user_id="user-1",
        product_id="am_app",
        agent_type="fin_portfolio",
        channel="user_app",
        title="Test",
        created_at=now,
        updated_at=now,
    )
    data = dto.model_dump(mode="json")
    assert SessionResponse.model_validate(data).id == session_id


def test_context_response_structure() -> None:
    now = datetime.now(timezone.utc)
    session_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    ctx = ContextResponse(
        session_id=session_id,
        messages=[
            MessageResponse(
                id=msg_id,
                session_id=session_id,
                role=MessageRole.user,
                content="Hi",
                created_at=now,
            )
        ],
    )
    assert ctx.messages[0].role == MessageRole.user


def test_session_list_response() -> None:
    now = datetime.now(timezone.utc)
    listed = SessionListResponse(
        items=[
            SessionResponse(
                id=uuid.uuid4(),
                user_id="u1",
                product_id="am_app",
                agent_type="fin_portfolio",
                channel="user_app",
                title="Chat",
                created_at=now,
                updated_at=now,
            )
        ],
        total=1,
        limit=50,
        offset=0,
    )
    assert listed.total == 1


def test_feedback_response_from_attributes() -> None:
    now = datetime.now(timezone.utc)

    class Row:
        id = uuid.uuid4()
        user_id = "user-1"
        session_id = uuid.uuid4()
        message_id = None
        agent_type = "fin_portfolio"
        rating = "up"
        comment = None
        trace_id = None
        created_at = now

    dto = FeedbackResponse.model_validate(Row())
    assert dto.rating == "up"

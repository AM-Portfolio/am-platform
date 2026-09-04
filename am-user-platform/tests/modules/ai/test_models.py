"""Model metadata tests — no Postgres required."""

from __future__ import annotations

import uuid

from am_user_platform.modules.ai.models.db import (
    AI_SCHEMA,
    AiFeedback,
    AiMessage,
    AiSession,
    MessageRole,
)


def _column_names(model) -> set[str]:
    return {column.name for column in model.__table__.columns}


def test_ai_schema_constant() -> None:
    assert AI_SCHEMA == "ai"


def test_session_table_in_ai_schema() -> None:
    assert AiSession.__table__.schema == "ai"
    assert AiSession.__tablename__ == "ai_sessions"


def test_session_columns() -> None:
    cols = _column_names(AiSession)
    assert {
        "id",
        "user_id",
        "product_id",
        "agent_type",
        "channel",
        "title",
        "org_id",
        "created_at",
        "updated_at",
        "deleted_at",
    }.issubset(cols)


def test_message_table_and_tokens_used() -> None:
    assert AiMessage.__table__.schema == "ai"
    assert AiMessage.__tablename__ == "ai_messages"
    cols = _column_names(AiMessage)
    assert "tokens_used" in cols
    assert "session_id" in cols
    assert "widget_params" in cols
    assert "tools_used" in cols


def test_feedback_table() -> None:
    assert AiFeedback.__table__.schema == "ai"
    assert AiFeedback.__tablename__ == "ai_feedback"
    cols = _column_names(AiFeedback)
    assert {"user_id", "session_id", "message_id", "rating", "agent_type"}.issubset(cols)


def test_message_role_enum_values() -> None:
    assert MessageRole.user.value == "user"
    assert MessageRole.assistant.value == "assistant"
    assert MessageRole.system.value == "system"


def test_all_three_tables_registered() -> None:
    from am_user_platform.core.database import Base

    table_names = {t.name for t in Base.metadata.sorted_tables}
    assert table_names == {"ai_sessions", "ai_messages", "ai_feedback"}
    for table in Base.metadata.sorted_tables:
        assert table.schema == "ai"


def test_session_indexes() -> None:
    index_names = {index.name for index in AiSession.__table__.indexes}
    assert "ix_ai_sessions_user_product_agent_updated" in index_names


def test_message_indexes() -> None:
    index_names = {index.name for index in AiMessage.__table__.indexes}
    assert "ix_ai_messages_session_created" in index_names


def test_foreign_keys() -> None:
    session_fks = {fk.target_fullname for fk in AiMessage.__table__.foreign_keys}
    assert "ai.ai_sessions.id" in session_fks


def test_session_model_instantiation() -> None:
    session = AiSession(
        id=uuid.uuid4(),
        user_id="user-123",
        product_id="am_app",
        agent_type="fin_portfolio",
        channel="user_app",
        title="Portfolio chat",
    )
    assert session.product_id == "am_app"
    assert session.agent_type == "fin_portfolio"

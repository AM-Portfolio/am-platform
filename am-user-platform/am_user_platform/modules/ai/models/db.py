from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from am_user_platform.core.database import Base

AI_SCHEMA = "ai"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AiSession(Base):
    __tablename__ = "ai_sessions"
    __table_args__ = (
        Index(
            "ix_ai_sessions_user_product_agent_updated",
            "user_id",
            "product_id",
            "agent_type",
            "updated_at",
        ),
        {"schema": AI_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="user_app")
    title: Mapped[str] = mapped_column(String(256), nullable=False, default="New chat")
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    messages: Mapped[list[AiMessage]] = relationship(
        "AiMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="AiMessage.created_at",
    )
    feedback: Mapped[list[AiFeedback]] = relationship(
        "AiFeedback",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class AiMessage(Base):
    __tablename__ = "ai_messages"
    __table_args__ = (
        Index("ix_ai_messages_session_created", "session_id", "created_at"),
        {"schema": AI_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AI_SCHEMA}.ai_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(
            MessageRole,
            name="message_role",
            schema=AI_SCHEMA,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    widget_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    widget_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tools_used: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    session: Mapped[AiSession] = relationship("AiSession", back_populates="messages")


class AiFeedback(Base):
    __tablename__ = "ai_feedback"
    __table_args__ = (
        Index("ix_ai_feedback_user_created", "user_id", "created_at"),
        Index("ix_ai_feedback_session_message", "session_id", "message_id"),
        {"schema": AI_SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AI_SCHEMA}.ai_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{AI_SCHEMA}.ai_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    session: Mapped[AiSession] = relationship("AiSession", back_populates="feedback")


def ensure_ai_schema_sql() -> str:
    return f"CREATE SCHEMA IF NOT EXISTS {AI_SCHEMA}"


def schema_create_statement() -> str:
    """Documented DDL entry point (tables created via SQLAlchemy metadata)."""
    return ensure_ai_schema_sql()

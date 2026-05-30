import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from am_subscription.core.database import Base

# Prefixed table names — Lago owns `subscriptions`, `customers`, etc. in the same DB.
TABLE_PREFIX = "am_"


class SubscriptionState(str, enum.Enum):
    trial = "trial"
    active = "active"
    past_due = "past_due"
    paused = "paused"
    suspended = "suspended"
    cancelled = "cancelled"
    expired = "expired"


class Subscription(Base):
    __tablename__ = f"{TABLE_PREFIX}subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    plan_code: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[SubscriptionState] = mapped_column(
        Enum(SubscriptionState, name="am_subscription_state"),
        default=SubscriptionState.active,
    )
    provider: Mapped[str] = mapped_column(String(32), default="lago")
    provider_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    billing_interval: Mapped[str] = mapped_column(String(16), default="monthly")
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ProviderMap(Base):
    __tablename__ = f"{TABLE_PREFIX}provider_maps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="lago")
    external_customer_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MeterBuffer(Base):
    __tablename__ = f"{TABLE_PREFIX}meter_buffers"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_am_meter_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    metric_code: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(256))
    properties_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SubscriptionAudit(Base):
    __tablename__ = f"{TABLE_PREFIX}subscription_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_state: Mapped[str] = mapped_column(String(32))
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
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


class ReferralCodeStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class AttributionStatus(str, enum.Enum):
    pending = "pending"
    qualified = "qualified"
    rewarded = "rewarded"
    rejected = "rejected"


class GrantScheduleKind(str, enum.Enum):
    trial = "trial"
    referral_reward = "referral_reward"


class GrantScheduleStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    cancelled = "cancelled"


class Subscription(Base):
    __tablename__ = f"{TABLE_PREFIX}subscriptions"
    __table_args__ = (
        Index(
            "uq_am_subscriptions_trial_email_fp",
            "trial_email_fingerprint",
            unique=True,
            postgresql_where=text("trial_email_fingerprint IS NOT NULL"),
            sqlite_where=text("trial_email_fingerprint IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    plan_code: Mapped[str] = mapped_column(String(64), index=True)
    state: Mapped[SubscriptionState] = mapped_column(
        Enum(SubscriptionState, name="am_subscription_state"),
        default=SubscriptionState.active,
    )
    provider: Mapped[str] = mapped_column(String(32), default="lago")
    provider_subscription_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    billing_interval: Mapped[str] = mapped_column(String(16), default="monthly")
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Timed Pro / referral grant metadata (Phase 3)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=False)
    grant_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trial_pro_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    referral_pro_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_email_fingerprint: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    trial_starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="lago")
    external_customer_id: Mapped[str] = mapped_column(
        String(128), unique=True, index=True
    )
    provider_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MeterBuffer(Base):
    __tablename__ = f"{TABLE_PREFIX}meter_buffers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_am_meter_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    metric_code: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(256))
    properties_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SubscriptionAudit(Base):
    __tablename__ = f"{TABLE_PREFIX}subscription_audits"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    actor: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    next_state: Mapped[str] = mapped_column(String(32))
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ReferralCode(Base):
    __tablename__ = f"{TABLE_PREFIX}referral_codes"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_am_referral_codes_user"),
        UniqueConstraint("code", name="uq_am_referral_codes_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    code: Mapped[str] = mapped_column(String(8), index=True)
    status: Mapped[ReferralCodeStatus] = mapped_column(
        Enum(ReferralCodeStatus, name="am_referral_code_status"),
        default=ReferralCodeStatus.active,
    )
    qualified_count: Mapped[int] = mapped_column(Integer, default=0)
    owner_email_fingerprint: Mapped[str | None] = mapped_column(
        String(256), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ReferralAttribution(Base):
    __tablename__ = f"{TABLE_PREFIX}referral_attributions"
    __table_args__ = (
        UniqueConstraint("referee_user_id", name="uq_am_referral_attr_referee"),
        Index("ix_am_referral_attr_referrer_status", "referrer_user_id", "status"),
        Index(
            "uq_am_referral_attr_device_active",
            "device_id",
            unique=True,
            postgresql_where=text("device_id IS NOT NULL AND status <> 'rejected'"),
            sqlite_where=text("device_id IS NOT NULL AND status <> 'rejected'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referee_user_id: Mapped[str] = mapped_column(String(128), index=True)
    referrer_user_id: Mapped[str] = mapped_column(String(128), index=True)
    code: Mapped[str] = mapped_column(String(8), index=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[AttributionStatus] = mapped_column(
        Enum(AttributionStatus, name="am_referral_attribution_status"),
        default=AttributionStatus.pending,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    referee_email_fingerprint: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_idempotency_key: Mapped[str | None] = mapped_column(
        String(256), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReferralReward(Base):
    __tablename__ = f"{TABLE_PREFIX}referral_rewards"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_am_referral_reward_idem"),
        Index(
            "ix_am_referral_rewards_beneficiary_granted",
            "beneficiary_user_id",
            "granted_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    attribution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{TABLE_PREFIX}referral_attributions.id"),
        index=True,
    )
    beneficiary_user_id: Mapped[str] = mapped_column(String(128), index=True)
    reward_type: Mapped[str] = mapped_column(String(32), default="pro_days")
    days: Mapped[int] = mapped_column(Integer, default=14)
    plan_code: Mapped[str] = mapped_column(String(64), default="am_pro")
    idempotency_key: Mapped[str] = mapped_column(String(256))
    granted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class GrantSchedule(Base):
    __tablename__ = f"{TABLE_PREFIX}grant_schedules"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_am_grant_schedule_idem"),
        Index("ix_am_grant_schedules_due", "status", "execute_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    kind: Mapped[GrantScheduleKind] = mapped_column(
        Enum(GrantScheduleKind, name="am_grant_schedule_kind")
    )
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    execute_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[GrantScheduleStatus] = mapped_column(
        Enum(GrantScheduleStatus, name="am_grant_schedule_status"),
        default=GrantScheduleStatus.pending,
    )
    idempotency_key: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

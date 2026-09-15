from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from am_subscription.core.config import SubscriptionSettings, get_settings
from am_subscription.core.log_utils import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: SubscriptionSettings | None = None):
    global _engine, _session_factory
    if _engine is None:
        settings = settings or get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            connect_args=settings.engine_connect_args,
        )
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def init_db() -> None:
    from am_subscription.models import db as models  # noqa: F401

    settings = get_settings()
    engine = get_engine(settings)
    logger.info(
        "Initializing database schema",
        extra={
            "db_host": settings.effective_postgres_host,
            "db_name": settings.db_name,
            "tables": [t.name for t in Base.metadata.sorted_tables],
        },
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_subscription_grant_columns)
    logger.info("Database schema ready")


def _ensure_subscription_grant_columns(sync_conn) -> None:
    """Best-effort ADD COLUMN for existing Postgres DBs (create_all won't alter)."""
    dialect = sync_conn.dialect.name
    if dialect != "postgresql":
        return
    statements = [
        "ALTER TABLE am_subscriptions ADD COLUMN IF NOT EXISTS is_paid BOOLEAN DEFAULT FALSE",
        "ALTER TABLE am_subscriptions ADD COLUMN IF NOT EXISTS grant_source VARCHAR(32)",
        "ALTER TABLE am_subscriptions ADD COLUMN IF NOT EXISTS trial_pro_expires_at TIMESTAMPTZ",
        "ALTER TABLE am_subscriptions ADD COLUMN IF NOT EXISTS referral_pro_expires_at TIMESTAMPTZ",
        "ALTER TABLE am_subscriptions ADD COLUMN IF NOT EXISTS trial_email_fingerprint VARCHAR(256)",
        "ALTER TABLE am_subscriptions ADD COLUMN IF NOT EXISTS trial_starts_at TIMESTAMPTZ",
    ]
    for sql in statements:
        sync_conn.exec_driver_sql(sql)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from am_user_platform.core.config import UserPlatformSettings, get_settings
from am_user_platform.core.log_utils import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(settings: UserPlatformSettings | None = None):
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
    """Create schema ai and tables from registered SQLAlchemy models."""
    # Import models so they register on Base.metadata before create_all.
    from am_user_platform.modules.ai import models as ai_models  # noqa: F401

    settings = get_settings()
    engine = get_engine(settings)
    tables = [t.name for t in Base.metadata.sorted_tables]
    logger.info(
        "Initializing database schema",
        extra={
            "db_host": settings.effective_postgres_host,
            "db_name": settings.db_name,
            "schema": ai_models.AI_SCHEMA,
            "tables": tables,
        },
    )
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {ai_models.AI_SCHEMA}"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema ready", extra={"table_count": len(tables)})


async def ping_db(settings: UserPlatformSettings | None = None) -> bool:
    settings = settings or get_settings()
    try:
        engine = get_engine(settings)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("Database ping failed")
        return False


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None

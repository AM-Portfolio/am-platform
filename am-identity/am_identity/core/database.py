from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

from am_identity.core.config import IdentitySettings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def initialize_database(settings: IdentitySettings) -> None:
    global _pool
    if not settings.database_url:
        logger.warning("DATABASE_URL is not configured; API key routes are unavailable")
        return

    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=settings.database_pool_size,
    )
    migration = (
        Path(__file__).resolve().parents[2] / "migrations" / "001_create_api_keys.sql"
    )
    async with _pool.acquire() as connection:
        await connection.execute(migration.read_text(encoding="utf-8"))


async def close_database() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_database_pool() -> asyncpg.Pool | None:
    return _pool

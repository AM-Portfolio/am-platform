"""Initial ai schema migration — Sprint C §2.

Run manually (same logic as startup init_db):

    python -m am_user_platform.modules.ai.migrations.versions.001_initial_ai_schema
"""

from __future__ import annotations

import asyncio

from am_user_platform.core.database import init_db
from am_user_platform.core.log_utils import get_logger

logger = get_logger("migration.001_initial_ai_schema")

MIGRATION_ID = "001_initial_ai_schema"
DESCRIPTION = "Create schema ai and tables ai_sessions, ai_messages, ai_feedback"


async def upgrade() -> None:
    logger.info("Running migration", extra={"id": MIGRATION_ID})
    await init_db()
    logger.info("Migration complete", extra={"id": MIGRATION_ID})


async def downgrade() -> None:
    """No downgrade in v1 — drop schema manually if needed."""
    raise NotImplementedError(
        "Downgrade not supported; use DROP SCHEMA ai CASCADE in non-prod only"
    )


def main() -> None:
    asyncio.run(upgrade())


if __name__ == "__main__":
    main()

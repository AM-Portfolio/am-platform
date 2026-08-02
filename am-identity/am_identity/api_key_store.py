from __future__ import annotations

import asyncio
import secrets
from typing import Any
from uuid import UUID, uuid4

import asyncpg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from am_identity.schemas.api_key import ApiKeyCreateRequest

_hasher = PasswordHasher(type=Type.ID)


class ApiKeyStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            """
            SELECT id, key_id, key_prefix, name, scope, created_at, last_used_at, revoked_at
            FROM api_keys
            WHERE user_id = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [dict(row) for row in rows]

    async def create(
        self, user_id: str, payload: ApiKeyCreateRequest
    ) -> dict[str, Any]:
        record_id = uuid4()
        key_id = f"asrx_{secrets.token_hex(8)}"
        secret = secrets.token_urlsafe(32)
        key_prefix = secret[:8]
        secret_hash = await asyncio.to_thread(_hasher.hash, secret)
        row = await self._pool.fetchrow(
            """
            INSERT INTO api_keys
                (id, user_id, key_id, key_prefix, secret_hash, name, scope)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, key_id, key_prefix, name, scope, created_at,
                      last_used_at, revoked_at
            """,
            record_id,
            user_id,
            key_id,
            key_prefix,
            secret_hash,
            payload.name.strip(),
            payload.scope,
        )
        return {**dict(row), "secret": secret}

    async def revoke(self, user_id: str, record_id: UUID) -> bool:
        result = await self._pool.execute(
            """
            UPDATE api_keys
            SET revoked_at = NOW()
            WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL
            """,
            record_id,
            user_id,
        )
        return result == "UPDATE 1"

    async def verify(self, key_id: str, secret: str) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            """
            SELECT id, user_id, secret_hash
            FROM api_keys
            WHERE key_id = $1 AND revoked_at IS NULL
            """,
            key_id,
        )
        if row is None:
            return None
        try:
            verified = await asyncio.to_thread(
                _hasher.verify, row["secret_hash"], secret
            )
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return None
        return dict(row) if verified else None

    async def mark_used(self, record_id: UUID) -> None:
        await self._pool.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
            record_id,
        )

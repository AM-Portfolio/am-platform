from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, status

STEP_UP_TTL_SECONDS = 300


@dataclass(frozen=True, slots=True)
class StepUpToken:
    token: str
    user_id: str
    created_at: float
    expires_at: float


class StepUpService:
    def __init__(self, *, ttl_seconds: int = STEP_UP_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._tokens: dict[str, StepUpToken] = {}

    def issue(self, user_id: str) -> StepUpToken:
        now = time.time()
        token = secrets.token_urlsafe(32)
        record = StepUpToken(
            token=token,
            user_id=user_id,
            created_at=now,
            expires_at=now + self._ttl_seconds,
        )
        with self._lock:
            self._tokens[token] = record
        return record

    def validate(self, token: str, *, user_id: str) -> StepUpToken:
        with self._lock:
            record = self._tokens.get(token)
        if record is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid step-up token")
        if record.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Step-up token mismatch")
        if time.time() >= record.expires_at:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Step-up token expired")
        return record


step_up_service = StepUpService()

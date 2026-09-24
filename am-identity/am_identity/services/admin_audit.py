from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from am_identity.schemas.admin import AuditEvent

_MAX_EVENTS = 200
_buffer: deque[AuditEvent] = deque(maxlen=_MAX_EVENTS)


def append_audit_event(
    *,
    action: str,
    actor_id: str | None = None,
    target_user_id: str | None = None,
    detail: str | None = None,
) -> None:
    _buffer.appendleft(
        AuditEvent(
            at=datetime.now(timezone.utc),
            actor_id=actor_id,
            action=action,
            target_user_id=target_user_id,
            detail=detail,
        )
    )


def list_audit_events(*, limit: int = 50) -> list[AuditEvent]:
    cap = max(1, min(limit, _MAX_EVENTS))
    return list(_buffer)[:cap]

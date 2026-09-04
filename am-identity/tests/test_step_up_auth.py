from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from am_identity.services.step_up_service import StepUpService


def test_issue_and_validate_step_up_token() -> None:
    service = StepUpService(ttl_seconds=300)
    record = service.issue("user-1")
    validated = service.validate(record.token, user_id="user-1")
    assert validated.user_id == "user-1"
    assert validated.token == record.token


def test_validate_rejects_other_user() -> None:
    service = StepUpService(ttl_seconds=300)
    record = service.issue("user-1")
    with pytest.raises(HTTPException) as exc:
        service.validate(record.token, user_id="user-2")
    assert exc.value.status_code == 403


def test_validate_rejects_expired_token() -> None:
    service = StepUpService(ttl_seconds=0)
    record = service.issue("user-1")
    time.sleep(0.01)
    with pytest.raises(HTTPException) as exc:
        service.validate(record.token, user_id="user-1")
    assert exc.value.status_code == 401

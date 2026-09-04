from __future__ import annotations

import base64
import hashlib
import secrets
import time

import pytest
from fastapi import HTTPException

from am_identity.services.bff_session_service import BffUser
from am_identity.services.device_link_service import (
    DeviceLinkService,
    DeviceLinkStartInput,
)


def _challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@pytest.fixture
def service() -> DeviceLinkService:
    return DeviceLinkService(ttl_seconds=120)


def _start(service: DeviceLinkService, verifier: str) -> tuple[str, str]:
    record = service.start(
        DeviceLinkStartInput(
            client="web",
            redirect_hint="am.asrax.in",
            code_challenge=_challenge_for(verifier),
            browser="Chrome",
            os="Windows",
            ip="192.168.1.10",
            user_agent="Mozilla/5.0",
        )
    )
    return record.device_link_id, record.confirmation_code


def test_start_returns_confirmation_code_and_stores_challenge(service: DeviceLinkService) -> None:
    verifier = secrets.token_urlsafe(32)
    device_link_id, confirmation_code = _start(service, verifier)
    assert len(confirmation_code) == 6
    assert confirmation_code.isdigit()
    preview = service.preview(device_link_id, user_id="user-1")
    assert preview["confirmation_code"] == confirmation_code


def test_poll_wrong_code_verifier_returns_403(service: DeviceLinkService) -> None:
    verifier = secrets.token_urlsafe(32)
    device_link_id, _ = _start(service, verifier)
    with pytest.raises(HTTPException) as exc:
        service.poll_status(device_link_id, code_verifier="wrong-verifier", ip=None, user_agent=None)
    assert exc.value.status_code == 403


def test_approve_wrong_confirmation_code_returns_400(service: DeviceLinkService) -> None:
    verifier = secrets.token_urlsafe(32)
    device_link_id, _ = _start(service, verifier)
    user = BffUser(sub="user-1", email="user@example.com")
    with pytest.raises(HTTPException) as exc:
        service.approve(
            device_link_id,
            user=user,
            confirmation_code="000000",
            device_name="Pixel",
            machine_label=None,
            access_token="access",
            refresh_token="refresh",
        )
    assert exc.value.status_code == 400


def test_approve_success_and_one_time_pickup(service: DeviceLinkService) -> None:
    verifier = secrets.token_urlsafe(32)
    device_link_id, confirmation_code = _start(service, verifier)
    user = BffUser(sub="user-1", email="user@example.com", preferred_username="user@example.com")
    approved = service.approve(
        device_link_id,
        user=user,
        confirmation_code=confirmation_code,
        device_name="Pixel 8",
        machine_label="Office laptop",
        access_token="access-token",
        refresh_token="refresh-token",
    )
    assert approved.status == "approved"

    pending_record, pending_user = service.poll_status(
        device_link_id,
        code_verifier=verifier,
        ip="192.168.1.10",
        user_agent="Mozilla/5.0",
    )
    assert pending_user is not None
    assert pending_user.sub == "user-1"
    assert pending_record.status == "consumed"
    assert pending_record.session_id is not None

    consumed_record, consumed_user = service.poll_status(
        device_link_id,
        code_verifier=verifier,
        ip="192.168.1.10",
        user_agent="Mozilla/5.0",
    )
    assert consumed_record.status == "consumed"
    assert consumed_user is not None


def test_expired_link(service: DeviceLinkService) -> None:
    expired_service = DeviceLinkService(ttl_seconds=0)
    verifier = secrets.token_urlsafe(32)
    record = expired_service.start(
        DeviceLinkStartInput(
            client="web",
            redirect_hint="am.asrax.in",
            code_challenge=_challenge_for(verifier),
            browser="Chrome",
            os="Windows",
            ip="192.168.1.10",
            user_agent="Mozilla/5.0",
        )
    )
    time.sleep(0.01)
    status_record, user = expired_service.poll_status(
        record.device_link_id,
        code_verifier=verifier,
        ip=None,
        user_agent=None,
    )
    assert status_record.status == "expired"
    assert user is None


def test_deny_writes_audit(service: DeviceLinkService) -> None:
    verifier = secrets.token_urlsafe(32)
    device_link_id, _ = _start(service, verifier)
    service.deny(
        device_link_id,
        user_id="user-1",
        reason="not_me",
        ip="10.0.0.1",
        user_agent="mobile",
    )
    audit = service.list_audit()
    assert any(entry.event == "denied" for entry in audit)

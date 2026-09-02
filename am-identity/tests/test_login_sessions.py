from __future__ import annotations

from am_identity.services.login_session_service import LoginContext, LoginSessionService


def test_new_machine_trust_key_creates_security_event() -> None:
    service = LoginSessionService()
    result = service.record_login(
        LoginContext(
            user_id="user-1",
            email="user@example.com",
            client_type="web",
            browser="Chrome",
            os="Windows",
            ip="203.0.113.10",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            machine_trust_key="machine-key-1",
        )
    )
    assert result.is_new_device is True
    assert result.security_event is not None
    assert result.security_event.type == "new_device_login"


def test_same_machine_trust_key_second_login_no_push_event() -> None:
    service = LoginSessionService()
    ctx = LoginContext(
        user_id="user-1",
        email="user@example.com",
        client_type="web",
        browser="Firefox",
        os="Windows",
        ip="203.0.113.10",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        machine_trust_key="machine-key-1",
    )
    first = service.record_login(ctx)
    second = service.record_login(
        LoginContext(
            user_id=ctx.user_id,
            email=ctx.email,
            client_type="web",
            browser="Safari",
            os=ctx.os,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
            machine_trust_key=ctx.machine_trust_key,
        )
    )
    assert first.is_new_device is True
    assert second.is_new_device is False
    assert second.security_event is None
    sessions = service.list_login_sessions("user-1")
    assert len(sessions) == 2


def test_security_event_ack() -> None:
    service = LoginSessionService()
    result = service.record_login(
        LoginContext(
            user_id="user-1",
            email="user@example.com",
            client_type="web",
            browser="Chrome",
            os="Windows",
            ip="203.0.113.10",
            user_agent="Mozilla/5.0",
            machine_trust_key="machine-key-2",
        )
    )
    assert result.security_event is not None
    acked = service.acknowledge_security_event("user-1", result.security_event.event_id)
    assert acked.acknowledged is True
    pending = service.list_security_events("user-1")
    assert pending == ()

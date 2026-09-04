from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from am_identity.main import app
from am_identity.services.web_otp_service import WebOtpService


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def otp_service(monkeypatch: pytest.MonkeyPatch) -> WebOtpService:
    service = WebOtpService()
    monkeypatch.setattr("am_identity.api.web_otp_router.web_otp_service", service)
    return service


def test_mobile_ua_blocked(client: TestClient) -> None:
    response = client.post(
        "/auth/web/otp/send",
        json={"channel": "email", "destination": "user@example.com"},
        headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 8)"},
    )
    assert response.status_code == 403


def test_send_email_dispatches_branded_mail(
    client: TestClient,
    otp_service: WebOtpService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[str, str]] = []

    def fake_send(*, to_email: str, code: str, expires_minutes: int) -> None:
        sent.append((to_email, code))

    async def resolve(_provider: object, _channel: str, _destination: str) -> dict[str, str]:
        return {"id": "user-otp", "email": "user@example.com"}

    monkeypatch.setattr("am_identity.services.web_otp_service.send_web_otp_email", fake_send)
    monkeypatch.setattr(
        "am_identity.api.web_otp_router._resolve_user",
        resolve,
    )

    response = client.post(
        "/auth/web/otp/send",
        json={"channel": "email", "destination": "user@example.com"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0"},
    )
    assert response.status_code == 200
    assert len(sent) == 1
    assert sent[0][0] == "user@example.com"
    assert len(sent[0][1]) == 6


def test_verify_sets_cookie(
    client: TestClient,
    otp_service: WebOtpService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolve(_provider: object, _channel: str, _destination: str) -> dict[str, str]:
        return {"id": "user-otp", "email": "user@example.com"}

    async def fake_issue(_provider: object, user_id: str) -> tuple[str, str | None, int | None]:
        return "access-token", "refresh-token", 3600

    monkeypatch.setattr("am_identity.services.web_otp_service.send_web_otp_email", lambda **_kwargs: None)
    monkeypatch.setattr(
        "am_identity.api.web_otp_router._resolve_user",
        resolve,
    )
    monkeypatch.setattr(
        "am_identity.api.web_otp_router.issue_web_session_tokens",
        fake_issue,
    )

    send_response = client.post(
        "/auth/web/otp/send",
        json={"channel": "email", "destination": "user@example.com"},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0"},
    )
    assert send_response.status_code == 200
    otp_session_id = send_response.json()["otp_session_id"]

    stored = otp_service._sessions[otp_session_id]  # noqa: SLF001
    verify_response = client.post(
        "/auth/web/otp/verify",
        json={"otp_session_id": otp_session_id, "code": stored.code},
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0"},
    )
    assert verify_response.status_code == 200
    assert "am_session" in verify_response.cookies
    body = verify_response.json()
    assert body["user"]["sub"] == "user-otp"
    assert body["tokens"]["access_token"] == "access-token"


def test_send_rate_limit(client: TestClient, otp_service: WebOtpService, monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(_provider: object, _channel: str, _destination: str) -> dict[str, str]:
        return {"id": "user-otp", "email": "user@example.com"}

    monkeypatch.setattr("am_identity.services.web_otp_service.send_web_otp_email", lambda **_kwargs: None)
    monkeypatch.setattr(
        "am_identity.api.web_otp_router._resolve_user",
        resolve,
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0"}
    for _ in range(3):
        response = client.post(
            "/auth/web/otp/send",
            json={"channel": "email", "destination": "user@example.com"},
            headers=headers,
        )
        assert response.status_code == 200

    blocked = client.post(
        "/auth/web/otp/send",
        json={"channel": "email", "destination": "user@example.com"},
        headers=headers,
    )
    assert blocked.status_code == 429

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


    response = client.post(
        "/auth/web/otp/send",
        json={"channel": "email", "destination": "user@example.com"},
        headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 8)"},
    )
    assert response.status_code == 403


def test_verify_sets_cookie(client: TestClient, otp_service: WebOtpService, monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(_provider: object, _channel: str, _destination: str) -> dict[str, str]:
        return {"id": "user-otp", "email": "user@example.com"}

    monkeypatch.setattr(
        "am_identity.api.web_otp_router._resolve_user",
        resolve,
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
    assert "access_token" not in body
    assert body["user"]["sub"] == "user-otp"


def test_send_rate_limit(client: TestClient, otp_service: WebOtpService, monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(_provider: object, _channel: str, _destination: str) -> dict[str, str]:
        return {"id": "user-otp", "email": "user@example.com"}

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

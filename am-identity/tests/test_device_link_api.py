from __future__ import annotations

import base64
import hashlib
import secrets

import pytest
from fastapi.testclient import TestClient

from am_identity.main import app


def _challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_device_link_status_allows_full_poll_budget(client: TestClient) -> None:
    verifier = secrets.token_urlsafe(32)
    start = client.post(
        "/auth/device-link/start",
        json={
            "client": "web",
            "redirect_hint": "am.asrax.in",
            "code_challenge": _challenge_for(verifier),
            "browser": "Chrome",
            "os": "Windows",
        },
    )
    assert start.status_code == 200
    device_link_id = start.json()["device_link_id"]

    for poll_index in range(35):
        response = client.get(
            f"/auth/device-link/{device_link_id}/status",
            params={"code_verifier": verifier},
        )
        assert response.status_code == 200, f"poll {poll_index} returned {response.status_code}"

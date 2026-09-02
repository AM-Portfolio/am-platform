from __future__ import annotations

from am_identity.email.templates import build_web_login_otp


def test_build_web_login_otp_formats_code() -> None:
    subject, html, plain = build_web_login_otp(code="482913", expires_minutes=5)
    assert subject == "Your Asrax sign-in code"
    assert "482 913" in html
    assert "482 913" in plain
    assert "noreply@asrax.in" in html
    assert "expires in 5 minutes" in plain

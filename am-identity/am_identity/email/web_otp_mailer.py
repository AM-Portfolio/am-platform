from __future__ import annotations

from fastapi import HTTPException, status

from am_identity.core.config import get_settings
from am_identity.email.smtp_client import SmtpNotConfiguredError, send_auth_email
from am_identity.email.templates import build_web_login_otp


def send_web_otp_email(*, to_email: str, code: str, expires_minutes: int) -> None:
    subject, html, plain = build_web_login_otp(code=code, expires_minutes=expires_minutes)
    try:
        send_auth_email(
            smtp=get_settings().resolved_smtp(),
            to_email=to_email,
            subject=subject,
            html_body=html,
            text_body=plain,
        )
    except SmtpNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to send OTP email: {exc}",
        ) from exc

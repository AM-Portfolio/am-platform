from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any

logger = logging.getLogger(__name__)


class SmtpNotConfiguredError(RuntimeError):
    pass


def send_auth_email(
    *,
    smtp: dict[str, Any],
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
) -> None:
    host = str(smtp.get("host") or "")
    user = str(smtp.get("user") or "")
    password = str(smtp.get("password") or "")
    from_addr = str(smtp.get("from_addr") or user)
    display = str(smtp.get("from_display_name") or "Asrax Accounts")
    port = int(smtp.get("port") or 465)
    use_ssl = bool(smtp.get("ssl", True))
    use_starttls = bool(smtp.get("starttls", False))

    if not host or not user or not password or not from_addr:
        raise SmtpNotConfiguredError(
            "SMTP is not configured (need SMTP_HOST/USER/PASSWORD/FROM or KEYCLOAK_SMTP_*)"
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = formataddr((display, from_addr))
    message["To"] = to_email
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
            server.sendmail(from_addr, [to_email], message.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            if use_starttls:
                server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.sendmail(from_addr, [to_email], message.as_string())

    logger.info("Auth email sent to %s subject=%s", to_email, subject)

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
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
    relay_url = str(smtp.get("http_relay_url") or os.getenv("SMTP_HTTP_RELAY_URL") or "").strip()
    if relay_url:
        _send_via_http_relay(
            relay_url=relay_url,
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            from_addr=str(smtp.get("from_addr") or ""),
            display=str(smtp.get("from_display_name") or "Asrax Accounts"),
            relay_token=str(smtp.get("http_relay_token") or os.getenv("SMTP_HTTP_RELAY_TOKEN") or ""),
        )
        return

    hosts = _host_list(smtp)
    user = str(smtp.get("user") or "")
    password = str(smtp.get("password") or "")
    from_addr = str(smtp.get("from_addr") or user)
    display = str(smtp.get("from_display_name") or "Asrax Accounts")
    port = int(smtp.get("port") or 465)
    use_ssl = bool(smtp.get("ssl", True))
    use_starttls = bool(smtp.get("starttls", False))

    if not hosts or not user or not password or not from_addr:
        raise SmtpNotConfiguredError(
            "SMTP is not configured (need SMTP_HOST/USER/PASSWORD/FROM or SMTP_HTTP_RELAY_URL)"
        )

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = formataddr((display, from_addr))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain="asrax.in")
    message.attach(MIMEText(text_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))
    raw = message.as_string()

    errors: list[str] = []
    for host in hosts:
        try:
            _send_smtp(
                host=host,
                port=port,
                use_ssl=use_ssl,
                use_starttls=use_starttls,
                user=user,
                password=password,
                from_addr=from_addr,
                to_email=to_email,
                raw_message=raw,
            )
            logger.info("Auth email sent to %s via %s subject=%s", to_email, host, subject)
            return
        except TimeoutError as exc:
            errors.append(f"{host}: TLS/connect timeout ({exc})")
            logger.warning("SMTP timeout host=%s error=%s", host, exc)
        except OSError as exc:
            errors.append(f"{host}: {type(exc).__name__}: {exc}")
            logger.warning("SMTP OS error host=%s error=%s", host, exc)
        except smtplib.SMTPException as exc:
            errors.append(f"{host}: {type(exc).__name__}: {exc}")
            logger.warning("SMTP protocol error host=%s error=%s", host, exc)

    joined = "; ".join(errors) if errors else "unknown SMTP failure"
    if any("timeout" in e.lower() for e in errors) and any(
        h.endswith(".zoho.in") for h in hosts
    ):
        joined += (
            ". Contabo egress cannot complete TLS to *.zoho.in; "
            "set SMTP_HTTP_RELAY_URL or switch SMTP_HOST to smtp.gmail.com / SES / Brevo"
        )
    raise RuntimeError(f"Failed to send auth email: {joined}")


def _host_list(smtp: dict[str, Any]) -> list[str]:
    raw = str(smtp.get("host") or "")
    return [part.strip() for part in raw.split(",") if part.strip()]


def _send_smtp(
    *,
    host: str,
    port: int,
    use_ssl: bool,
    use_starttls: bool,
    user: str,
    password: str,
    from_addr: str,
    to_email: str,
    raw_message: str,
) -> None:
    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
            server.login(user, password)
            server.sendmail(from_addr, [to_email], raw_message)
        return

    with smtplib.SMTP(host, port, timeout=20) as server:
        if use_starttls:
            server.starttls(context=ssl.create_default_context())
        server.login(user, password)
        server.sendmail(from_addr, [to_email], raw_message)


def _send_via_http_relay(
    *,
    relay_url: str,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str,
    from_addr: str,
    display: str,
    relay_token: str,
) -> None:
    payload = {
        "to": to_email,
        "subject": subject,
        "html": html_body,
        "text": text_body,
        "from_addr": from_addr,
        "from_display_name": display,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        # Free ngrok serves an interstitial HTML page unless this header is set.
        "ngrok-skip-browser-warning": "true",
        "User-Agent": "am-identity-smtp-relay/1.0",
    }
    if relay_token:
        headers["Authorization"] = f"Bearer {relay_token}"
    req = urllib.request.Request(
        relay_url.rstrip("/") + "/send",
        data=data,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                raise RuntimeError(f"HTTP relay status {resp.status}: {body}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP relay status {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"HTTP relay unreachable: {exc}") from exc

    logger.info("Auth email sent to %s via HTTP relay subject=%s", to_email, subject)

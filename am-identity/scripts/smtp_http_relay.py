#!/usr/bin/env python3
"""Local HTTP->SMTP relay so cluster pods can send mail via a reachable host.

Contabo egress cannot complete TLS to *.zoho.in. Run this on a machine that can
reach Zoho (e.g. developer laptop), expose with ngrok, set SMTP_HTTP_RELAY_URL.
"""

from __future__ import annotations

import json
import os
import secrets
import smtplib
import ssl
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _smtp_cfg() -> dict[str, str | int | bool]:
    host = os.environ.get("SMTP_HOST") or os.environ.get("KEYCLOAK_SMTP_HOST") or ""
    user = os.environ.get("SMTP_USER") or os.environ.get("KEYCLOAK_SMTP_USER") or ""
    password = (
        os.environ.get("SMTP_PASSWORD") or os.environ.get("KEYCLOAK_SMTP_PASSWORD") or ""
    )
    from_addr = (
        os.environ.get("SMTP_FROM") or os.environ.get("KEYCLOAK_SMTP_FROM") or user
    )
    display = (
        os.environ.get("SMTP_FROM_DISPLAY_NAME")
        or os.environ.get("KEYCLOAK_SMTP_FROM_DISPLAY_NAME")
        or "Asrax Accounts"
    )
    port = int(os.environ.get("SMTP_PORT") or os.environ.get("KEYCLOAK_SMTP_PORT") or 465)
    ssl_on = (
        os.environ.get("SMTP_SSL") or os.environ.get("KEYCLOAK_SMTP_SSL") or "true"
    ).lower() in ("1", "true", "yes")
    starttls = (
        os.environ.get("SMTP_STARTTLS")
        or os.environ.get("KEYCLOAK_SMTP_STARTTLS")
        or "false"
    ).lower() in ("1", "true", "yes")
    if not host or not user or not password:
        raise SystemExit("SMTP_HOST/USER/PASSWORD required (or KEYCLOAK_SMTP_*)")
    return {
        "host": host,
        "user": user,
        "password": password,
        "from_addr": from_addr,
        "display": display,
        "port": port,
        "ssl": ssl_on,
        "starttls": starttls,
    }


TOKEN = os.environ.get("SMTP_HTTP_RELAY_TOKEN") or secrets.token_urlsafe(24)
CFG: dict[str, str | int | bool] = {}


def _send(payload: dict) -> None:
    to_email = str(payload.get("to") or "").strip()
    subject = str(payload.get("subject") or "").strip()
    html_body = str(payload.get("html") or "")
    text_body = str(payload.get("text") or "")
    from_addr = str(payload.get("from_addr") or CFG["from_addr"])
    display = str(payload.get("from_display_name") or CFG["display"])
    if not to_email or not subject:
        raise ValueError("to and subject are required")

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = formataddr((display, from_addr))
    message["To"] = to_email
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain="asrax.in")
    message.attach(MIMEText(text_body or subject, "plain", "utf-8"))
    message.attach(MIMEText(html_body or text_body or subject, "html", "utf-8"))
    raw = message.as_string()

    host = str(CFG["host"])
    port = int(CFG["port"])
    user = str(CFG["user"])
    password = str(CFG["password"])
    if CFG["ssl"]:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
            server.sendmail(from_addr, [to_email], raw)
        return
    with smtplib.SMTP(host, port, timeout=30) as server:
        if CFG["starttls"]:
            server.starttls(context=ssl.create_default_context())
        server.login(user, password)
        server.sendmail(from_addr, [to_email], raw)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _auth_ok(self) -> bool:
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {TOKEN}"

    def do_GET(self) -> None:
        if self.path.rstrip("/") == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/send":
            self.send_error(404)
            return
        if not self._auth_ok():
            self.send_error(401, "unauthorized")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
            _send(payload)
        except Exception as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    _load_dotenv(root / ".secrets.prod.env")
    _load_dotenv(root / ".secrets.preprod.env")
    global CFG
    CFG = _smtp_cfg()
    port = int(os.environ.get("SMTP_HTTP_RELAY_PORT") or 8790)
    print(f"relay listening on 0.0.0.0:{port}", flush=True)
    print(f"SMTP_HTTP_RELAY_TOKEN={TOKEN}", flush=True)
    print(f"upstream SMTP host={CFG['host']} user={CFG['user']}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

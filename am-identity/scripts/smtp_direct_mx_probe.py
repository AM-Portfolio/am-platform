import os
import smtplib
import time
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid

to_addr = os.environ.get("SMTP_TEST_TO", "ssd2658@gmail.com")
from_addr = os.environ.get("SMTP_FROM", "noreply@asrax.in")
display = os.environ.get("SMTP_FROM_DISPLAY_NAME", "Asrax Accounts")
mx_host = "gmail-smtp-in.l.google.com"

msg = MIMEMultipart("alternative")
msg["Subject"] = "Asrax direct-MX probe"
msg["From"] = formataddr((display, from_addr))
msg["To"] = to_addr
msg["Date"] = formatdate(localtime=False)
msg["Message-ID"] = make_msgid(domain="asrax.in")
msg.attach(MIMEText("Direct MX delivery from am-identity pod works.\n", "plain", "utf-8"))

with smtplib.SMTP(mx_host, 25, timeout=30) as server:
    server.ehlo("mail.asrax.in")
    server.sendmail(from_addr, [to_addr], msg.as_string())
print("SEND_OK via", mx_host, "id", msg["Message-ID"])

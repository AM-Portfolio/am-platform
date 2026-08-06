import os
import smtplib
import ssl

host = os.environ.get("SMTP_TEST_HOST", "smtp.zoho.eu")
user = os.environ["SMTP_USER"]
password = os.environ["SMTP_PASSWORD"]
from_addr = os.environ.get("SMTP_FROM", user)
to_addr = os.environ.get("SMTP_TEST_TO", user)

ctx = ssl.create_default_context()
with smtplib.SMTP_SSL(host, 465, context=ctx, timeout=20) as server:
    server.login(user, password)
    server.sendmail(
        from_addr,
        [to_addr],
        f"From: {from_addr}\r\nTo: {to_addr}\r\nSubject: Asrax SMTP probe\r\n\r\nzoho.eu relay ok from am-identity pod\r\n",
    )
print("SEND_OK", host)

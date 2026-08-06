import smtplib
import ssl
import time

hosts = [
    ("smtp.gmail.com", 465, "ssl"),
    ("smtp.office365.com", 587, "starttls"),
    ("smtp-mail.outlook.com", 587, "starttls"),
    ("email-smtp.eu-west-1.amazonaws.com", 587, "starttls"),
]
for host, port, mode in hosts:
    t0 = time.time()
    try:
        if mode == "ssl":
            with smtplib.SMTP_SSL(
                host, port, context=ssl.create_default_context(), timeout=12
            ) as s:
                s.ehlo()
                print(host, port, "ok", round(time.time() - t0, 2))
        else:
            with smtplib.SMTP(host, port, timeout=12) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.ehlo()
                print(host, port, "ok", round(time.time() - t0, 2))
    except Exception as e:
        print(host, port, "FAIL", round(time.time() - t0, 2), type(e).__name__, str(e)[:100])

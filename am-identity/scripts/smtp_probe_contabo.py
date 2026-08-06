import smtplib
import ssl

for host, port, mode in [
    ("smtp.contabo.com", 587, "starttls"),
    ("mail.contabo.com", 587, "starttls"),
    ("smtp.contabo.com", 465, "ssl"),
]:
    try:
        if mode == "ssl":
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=10) as s:
                s.ehlo()
                print(host, port, "ok")
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                print(host, port, "ok")
    except Exception as e:
        print(host, port, "FAIL", type(e).__name__, str(e)[:100])

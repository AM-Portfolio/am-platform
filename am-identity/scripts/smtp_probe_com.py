import socket, ssl, time, smtplib, os

hosts = [
    "smtp.zoho.com",
    "smtppro.zoho.com",
    "smtp.zoho.eu",
]
for host in hosts:
    for port, mode in ((465, "ssl"), (587, "starttls")):
        t0 = time.time()
        try:
            if mode == "ssl":
                ctx = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, context=ctx, timeout=12) as s:
                    s.ehlo()
                    print(host, port, mode, "ok", round(time.time() - t0, 2))
            else:
                with smtplib.SMTP(host, port, timeout=12) as s:
                    s.ehlo()
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                    print(host, port, mode, "ok", round(time.time() - t0, 2))
        except Exception as e:
            print(host, port, mode, "FAIL", round(time.time() - t0, 2), type(e).__name__, str(e)[:120])

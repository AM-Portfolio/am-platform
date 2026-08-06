import socket, ssl, time

hosts = [
    ("smtppro.zoho.in", 465),
    ("smtppro.zoho.in", 587),
    ("smtp.zoho.in", 465),
    ("smtp.zoho.in", 587),
    ("smtp.zoho.com", 465),
    ("smtp.zoho.com", 587),
]

for host, port in hosts:
    t0 = time.time()
    try:
        raw = socket.create_connection((host, port), timeout=8)
        print("tcp", host, port, "ok", round(time.time() - t0, 2))
    except Exception as e:
        print("tcp", host, port, "FAIL", type(e).__name__, str(e))
        continue
    try:
        if port == 465:
            ctx = ssl.create_default_context()
            ss = ctx.wrap_socket(raw, server_hostname=host)
            print("  ssl", host, port, "ok", round(time.time() - t0, 2), ss.version())
            ss.close()
        else:
            import smtplib

            raw.close()
            smtp = smtplib.SMTP(host, port, timeout=12)
            smtp.ehlo()
            smtp.starttls(context=ssl.create_default_context())
            print("  starttls", host, port, "ok", round(time.time() - t0, 2))
            smtp.quit()
    except Exception as e:
        print("  tls", host, port, "FAIL", round(time.time() - t0, 2), type(e).__name__, str(e))

# Control: TLS to a known good HTTPS endpoint
t0 = time.time()
try:
    ctx = ssl.create_default_context()
    with socket.create_connection(("www.google.com", 443), timeout=8) as sock:
        with ctx.wrap_socket(sock, server_hostname="www.google.com") as ss:
            print("control https google ok", round(time.time() - t0, 2), ss.version())
except Exception as e:
    print("control https google FAIL", type(e).__name__, str(e))

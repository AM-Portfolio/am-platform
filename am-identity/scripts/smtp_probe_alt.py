import socket, ssl, time

# Common alternate submission ports
targets = [
    ("smtppro.zoho.in", 25),
    ("smtppro.zoho.in", 2525),
    ("smtp.gmail.com", 465),
    ("mail.zoho.in", 443),
]
for host, port in targets:
    t0 = time.time()
    try:
        raw = socket.create_connection((host, port), timeout=6)
        print("tcp", host, port, "ok", round(time.time() - t0, 2))
    except Exception as e:
        print("tcp", host, port, "FAIL", type(e).__name__, str(e)[:80])
        continue
    try:
        ctx = ssl.create_default_context()
        if port in (443, 465):
            ss = ctx.wrap_socket(raw, server_hostname=host)
            print("  tls", host, port, "ok", round(time.time() - t0, 2), ss.version())
            ss.close()
        else:
            banner = raw.recv(128)
            print("  banner", host, port, banner[:60])
            raw.close()
    except Exception as e:
        print("  tls/banner", host, port, "FAIL", round(time.time() - t0, 2), type(e).__name__, str(e)[:100])

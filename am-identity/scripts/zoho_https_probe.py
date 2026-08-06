import socket, ssl, time

hosts = [
    "www.zoho.com",
    "www.zoho.in",
    "accounts.zoho.in",
    "mail.zoho.com",
    "cliq.zoho.in",
]
for host in hosts:
    t0 = time.time()
    try:
        raw = socket.create_connection((host, 443), timeout=6)
        ctx = ssl.create_default_context()
        ss = ctx.wrap_socket(raw, server_hostname=host)
        print(host, "ok", round(time.time() - t0, 2), ss.version())
        ss.close()
    except Exception as e:
        print(host, "FAIL", round(time.time() - t0, 2), type(e).__name__, str(e)[:100])

import socket, ssl, time

for host in [
    "accounts.zoho.com",
    "accounts.zoho.in",
    "accounts.zoho.eu",
    "mail.zoho.com",
    "mail.zoho.in",
    "www.zohoapis.in",
    "www.zohoapis.com",
]:
    t0 = time.time()
    try:
        raw = socket.create_connection((host, 443), timeout=8)
        ss = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        print(host, "ok", round(time.time() - t0, 2), ss.version())
        ss.close()
    except Exception as e:
        print(host, "FAIL", round(time.time() - t0, 2), type(e).__name__, str(e)[:80])

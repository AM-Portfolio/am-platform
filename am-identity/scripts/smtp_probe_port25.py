import smtplib
import socket
import ssl

# Direct submission to Gmail MX on port 25 (open relay won't work; just connectivity)
for host in ["gmail-smtp-in.l.google.com", "aspmx.l.google.com"]:
    try:
        s = socket.create_connection((host, 25), timeout=10)
        banner = s.recv(200)
        print(host, "banner", banner[:80])
        s.close()
    except Exception as e:
        print(host, "FAIL", type(e).__name__, str(e)[:100])

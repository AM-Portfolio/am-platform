import os, socket, ssl, time

host = os.environ.get("SMTP_HOST", "smtppro.zoho.in")
for port in (465, 587):
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=10)
        print("tcp", port, "ok", round(time.time() - t0, 2))
        if port == 465:
            ctx = ssl.create_default_context()
            try:
                ss = ctx.wrap_socket(s, server_hostname=host)
                print("ssl465 ok", round(time.time() - t0, 2), ss.version())
                ss.close()
            except Exception as e:
                print("ssl465 FAIL", round(time.time() - t0, 2), type(e).__name__, str(e))
        else:
            try:
                import smtplib

                s.close()
                smtp = smtplib.SMTP(host, 587, timeout=15)
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                print("starttls587 ok", round(time.time() - t0, 2))
                smtp.quit()
            except Exception as e:
                print("starttls587 FAIL", round(time.time() - t0, 2), type(e).__name__, str(e))
    except Exception as e:
        print("tcp", port, "FAIL", round(time.time() - t0, 2), type(e).__name__, str(e))

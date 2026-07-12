from __future__ import annotations

# Colors aligned with am_auth_ui / AppColors.
_NAVY_TOP = "#1A1A2E"
_NAVY_MID = "#16213E"
_NAVY_DEEP = "#0F3460"
_CTA = "#6C63FF"
_TEXT = "#2D3436"
_MUTED = "#636E72"


def _shell(*, preheader: str, headline: str, body: str, cta_label: str, cta_url: str) -> str:
    safe_url = cta_url.replace('"', "&quot;")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{headline}</title>
</head>
<body style="margin:0;padding:0;background:{_NAVY_TOP};font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(160deg,{_NAVY_TOP} 0%,{_NAVY_MID} 55%,{_NAVY_DEEP} 100%);background-color:{_NAVY_TOP};">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;">
          <tr>
            <td align="center" style="padding:0 8px 24px;">
              <div style="font-size:28px;font-weight:700;letter-spacing:0.08em;color:#FFFFFF;">ASRAX</div>
              <div style="margin-top:6px;font-size:13px;color:rgba(255,255,255,0.7);">AM Investment · Account</div>
              <div style="margin:14px auto 0;width:48px;height:3px;background:{_CTA};border-radius:2px;"></div>
            </td>
          </tr>
          <tr>
            <td style="background:#FFFFFF;border-radius:24px;padding:32px 28px;box-shadow:0 16px 40px rgba(0,0,0,0.28);">
              <h1 style="margin:0 0 12px;font-size:22px;line-height:1.3;color:{_TEXT};">{headline}</h1>
              <p style="margin:0 0 24px;font-size:15px;line-height:1.55;color:{_MUTED};">{body}</p>
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 20px;">
                <tr>
                  <td align="center" style="border-radius:12px;background:{_CTA};">
                    <a href="{safe_url}" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:600;color:#FFFFFF;text-decoration:none;border-radius:12px;">
                      {cta_label}
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 8px;font-size:12px;line-height:1.5;color:{_MUTED};word-break:break-all;">
                Or open this link:<br/>
                <a href="{safe_url}" style="color:{_CTA};">{safe_url}</a>
              </p>
              <p style="margin:16px 0 0;font-size:12px;color:{_MUTED};">This link expires in 12 hours.</p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:24px 8px 8px;font-size:12px;line-height:1.5;color:rgba(255,255,255,0.55);">
              If you did not expect this email, you can ignore it.<br/>
              asrax.in
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def build_verify_email(*, action_url: str) -> tuple[str, str, str]:
    subject = "Verify your Asrax email"
    html = _shell(
        preheader="Confirm your email to finish setting up your Asrax account.",
        headline="Verify your email",
        body="Confirm this address to finish setting up your Asrax account.",
        cta_label="Verify email",
        cta_url=action_url,
    )
    plain = (
        "Verify your Asrax email\n\n"
        "Confirm this address to finish setting up your Asrax account.\n\n"
        f"{action_url}\n\n"
        "This link expires in 12 hours.\n"
    )
    return subject, html, plain


def build_reset_password(*, action_url: str) -> tuple[str, str, str]:
    subject = "Reset your Asrax password"
    html = _shell(
        preheader="Choose a new password for your Asrax account.",
        headline="Reset your password",
        body=(
            "Choose a new password for your Asrax account. "
            "If you did not ask for this, you can ignore this message."
        ),
        cta_label="Reset password",
        cta_url=action_url,
    )
    plain = (
        "Reset your Asrax password\n\n"
        "Choose a new password for your Asrax account. "
        "If you did not ask for this, you can ignore this message.\n\n"
        f"{action_url}\n\n"
        "This link expires in 12 hours.\n"
    )
    return subject, html, plain

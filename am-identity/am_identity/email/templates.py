from __future__ import annotations

# Colors aligned with am_auth_ui / AppColors.
_NAVY_TOP = "#1A1A2E"
_NAVY_MID = "#16213E"
_NAVY_DEEP = "#0F3460"
_CTA = "#6C63FF"
_TEXT = "#2D3436"
_MUTED = "#636E72"
_PROMO_BG = "#F4F5FB"
_INSIGHT = "Track portfolios, markets, and trades in one Asrax workspace."


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
      <td align="center" style="padding:20px 12px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:440px;">
          <tr>
            <td align="center" style="padding:0 4px 14px;">
              <div style="font-size:22px;font-weight:700;letter-spacing:0.1em;color:#FFFFFF;">ASRAX</div>
              <div style="margin-top:4px;font-size:11px;letter-spacing:0.04em;color:rgba(255,255,255,0.65);">AM Investment</div>
            </td>
          </tr>
          <tr>
            <td style="background:#FFFFFF;border-radius:16px;padding:22px 22px 18px;box-shadow:0 12px 28px rgba(0,0,0,0.25);">
              <h1 style="margin:0 0 8px;font-size:18px;line-height:1.25;color:{_TEXT};">{headline}</h1>
              <p style="margin:0 0 18px;font-size:14px;line-height:1.5;color:{_MUTED};">{body}</p>
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 16px;">
                <tr>
                  <td align="center" style="border-radius:10px;background:{_CTA};">
                    <a href="{safe_url}" style="display:inline-block;padding:12px 26px;font-size:14px;font-weight:600;color:#FFFFFF;text-decoration:none;border-radius:10px;">
                      {cta_label}
                    </a>
                  </td>
                </tr>
              </table>
              <p style="margin:0 0 14px;font-size:11px;line-height:1.4;color:{_MUTED};text-align:center;">
                Link expires in 12 hours. Use the button above — do not forward this email.
              </p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_PROMO_BG};border-radius:10px;">
                <tr>
                  <td style="padding:10px 12px;font-size:12px;line-height:1.45;color:{_MUTED};">
                    <span style="display:inline-block;font-size:10px;font-weight:600;letter-spacing:0.06em;text-transform:uppercase;color:{_CTA};margin-bottom:4px;">Asrax tip</span><br/>
                    {_INSIGHT}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:16px 8px 4px;font-size:11px;line-height:1.55;color:rgba(255,255,255,0.55);">
              Questions? Contact Asrax Accounts<br/>
              <a href="mailto:noreply@asrax.in" style="color:rgba(255,255,255,0.75);text-decoration:none;">noreply@asrax.in</a>
              &nbsp;·&nbsp;
              <a href="https://asrax.in" style="color:rgba(255,255,255,0.75);text-decoration:none;">asrax.in</a>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:6px 8px 8px;font-size:10px;line-height:1.4;color:rgba(255,255,255,0.4);">
              If you did not expect this email, you can ignore it.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _plain(*, headline: str, body: str, action_url: str) -> str:
    return (
        f"{headline}\n\n"
        f"{body}\n\n"
        f"Open this link to continue:\n{action_url}\n\n"
        "This link expires in 12 hours.\n\n"
        f"{_INSIGHT}\n\n"
        "Questions? Contact Asrax Accounts — noreply@asrax.in · https://asrax.in\n"
    )


def build_verify_email(*, action_url: str) -> tuple[str, str, str]:
    subject = "Verify your Asrax email"
    body = "Confirm this address to finish setting up your Asrax account."
    html = _shell(
        preheader="Confirm your email to finish setting up your Asrax account.",
        headline="Verify your email",
        body=body,
        cta_label="Verify email",
        cta_url=action_url,
    )
    return subject, html, _plain(headline=subject, body=body, action_url=action_url)


def build_reset_password(*, action_url: str) -> tuple[str, str, str]:
    subject = "Reset your Asrax password"
    body = (
        "Choose a new password for your Asrax account. "
        "If you did not ask for this, you can ignore this message."
    )
    html = _shell(
        preheader="Choose a new password for your Asrax account.",
        headline="Reset your password",
        body=body,
        cta_label="Reset password",
        cta_url=action_url,
    )
    return subject, html, _plain(headline=subject, body=body, action_url=action_url)

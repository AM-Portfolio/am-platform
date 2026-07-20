from __future__ import annotations

# Colors aligned with am_auth_ui / AppColors.
_NAVY_TOP = "#1A1A2E"
_NAVY_MID = "#16213E"
_NAVY_DEEP = "#0F3460"
_CTA = "#6C63FF"
_TEXT = "#2D3436"
_MUTED = "#636E72"
_PROMO_BG = "#F4F5FB"
_VALUE = (
    "Asrax brings portfolios, markets, trades, and AI insights together "
    "so you can decide faster with clarity."
)
_FEATURES: tuple[tuple[str, str], ...] = (
    ("Portfolio", "Track holdings and performance in one place"),
    ("Markets", "Follow indices and instruments with live context"),
    ("Trade", "Manage orders and activity across portfolios"),
    ("AI insights", "Ask questions and surface analysis faster"),
)


def _feature_grid_html(*, compact: bool = False) -> str:
    pad = "8px 10px" if compact else "10px 12px"
    rows: list[str] = []
    for i in range(0, len(_FEATURES), 2):
        cells: list[str] = []
        for title, desc in _FEATURES[i : i + 2]:
            cells.append(f"""
                <td width="50%" valign="top" style="padding:4px;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                    style="background:{_PROMO_BG};border-radius:10px;">
                    <tr>
                      <td style="padding:{pad};">
                        <div style="font-size:12px;font-weight:700;color:{_TEXT};margin-bottom:3px;">{title}</div>
                        <div style="font-size:11px;line-height:1.4;color:{_MUTED};">{desc}</div>
                      </td>
                    </tr>
                  </table>
                </td>
                """)
        if len(cells) == 1:
            cells.append('<td width="50%"></td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:0 0 14px;">{"".join(rows)}</table>'
    )


def _shell(
    *,
    preheader: str,
    headline: str,
    body: str,
    cta_label: str,
    cta_url: str,
    app_home: str,
    show_feature_grid: bool = True,
    feature_compact: bool = False,
    secondary_cta_label: str | None = None,
    secondary_cta_url: str | None = None,
    value_line: str | None = None,
) -> str:
    """Render branded HTML. ``app_home`` must come from Vault AUTH_UI_BASE_URL at runtime."""
    if not app_home.strip():
        raise ValueError("app_home is required (set AUTH_UI_BASE_URL from Vault)")
    safe_url = cta_url.replace('"', "&quot;")
    home = app_home.rstrip("/").replace('"', "&quot;")
    features = _feature_grid_html(compact=feature_compact) if show_feature_grid else ""
    value_html = ""
    if value_line:
        value_html = (
            f'<p style="margin:0 0 14px;font-size:13px;line-height:1.5;color:{_MUTED};">'
            f"{value_line}</p>"
        )
    secondary = ""
    if secondary_cta_label and secondary_cta_url:
        sec = secondary_cta_url.replace('"', "&quot;")
        secondary = f"""
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 14px;">
                <tr>
                  <td align="center">
                    <a href="{sec}" style="font-size:13px;font-weight:600;color:{_CTA};text-decoration:none;">
                      {secondary_cta_label} →
                    </a>
                  </td>
                </tr>
              </table>
        """
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
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;">
          <tr>
            <td align="center" style="padding:0 4px 16px;">
              <div style="font-size:24px;font-weight:700;letter-spacing:0.12em;color:#FFFFFF;">ASRAX</div>
              <div style="margin-top:5px;font-size:12px;letter-spacing:0.04em;color:rgba(255,255,255,0.7);">AM Investment Platform</div>
              <div style="margin:12px auto 0;width:40px;height:3px;background:{_CTA};border-radius:2px;"></div>
            </td>
          </tr>
          <tr>
            <td style="background:#FFFFFF;border-radius:18px;padding:26px 24px 20px;box-shadow:0 14px 32px rgba(0,0,0,0.28);">
              <h1 style="margin:0 0 10px;font-size:20px;line-height:1.25;color:{_TEXT};">{headline}</h1>
              <p style="margin:0 0 16px;font-size:14px;line-height:1.55;color:{_MUTED};">{body}</p>
              {value_html}
              {features}
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto 14px;">
                <tr>
                  <td align="center" style="border-radius:10px;background:{_CTA};">
                    <a href="{safe_url}" style="display:inline-block;padding:13px 28px;font-size:14px;font-weight:600;color:#FFFFFF;text-decoration:none;border-radius:10px;">
                      {cta_label}
                    </a>
                  </td>
                </tr>
              </table>
              {secondary}
              <p style="margin:0;font-size:11px;line-height:1.4;color:{_MUTED};text-align:center;">
                Link expires in 12 hours. Use the button above — do not forward this email.
              </p>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:18px 8px 4px;font-size:11px;line-height:1.55;color:rgba(255,255,255,0.55);">
              Questions? Contact Asrax Accounts<br/>
              <a href="mailto:noreply@asrax.in" style="color:rgba(255,255,255,0.75);text-decoration:none;">noreply@asrax.in</a>
              &nbsp;·&nbsp;
              <a href="https://asrax.in" style="color:rgba(255,255,255,0.75);text-decoration:none;">asrax.in</a>
              &nbsp;·&nbsp;
              <a href="{home}" style="color:rgba(255,255,255,0.75);text-decoration:none;">Open app</a>
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


def _plain(
    *,
    headline: str,
    body: str,
    action_url: str,
    include_features: bool = True,
    value_line: str | None = None,
) -> str:
    parts = [headline, "", body, ""]
    if value_line:
        parts.extend([value_line, ""])
    if include_features:
        parts.append("Explore Asrax:")
        for title, desc in _FEATURES:
            parts.append(f"- {title}: {desc}")
        parts.append("")
    parts.extend(
        [
            f"Continue: {action_url}",
            "",
            "This link expires in 12 hours.",
            "",
            "Questions? Contact Asrax Accounts — noreply@asrax.in · https://asrax.in",
        ]
    )
    return "\n".join(parts)


def build_welcome_verify_email(
    *, action_url: str, app_home: str
) -> tuple[str, str, str]:
    """Marketing-ready welcome mail that also verifies email (single send).

    ``app_home`` must be the runtime AUTH_UI_BASE_URL from Vault (no hardcoded host).
    """
    subject = "Welcome to Asrax — verify your email"
    body = (
        "Your Asrax account is ready. Confirm your email to unlock the AM Investment "
        "workspace and start exploring portfolios, markets, and trades."
    )
    html = _shell(
        preheader="Welcome to Asrax — verify your email to get started.",
        headline="Welcome to Asrax",
        body=body,
        cta_label="Verify email",
        cta_url=action_url,
        app_home=app_home,
        show_feature_grid=True,
        feature_compact=False,
        secondary_cta_label="Explore Asrax",
        secondary_cta_url=app_home.rstrip("/"),
        value_line=_VALUE,
    )
    return (
        subject,
        html,
        _plain(
            headline=subject,
            body=body,
            action_url=action_url,
            include_features=True,
            value_line=_VALUE,
        ),
    )


def build_verify_email(*, action_url: str, app_home: str) -> tuple[str, str, str]:
    """Resend / verify path — same marketing welcome+verify experience."""
    return build_welcome_verify_email(action_url=action_url, app_home=app_home)


def build_reset_password(*, action_url: str, app_home: str) -> tuple[str, str, str]:
    subject = "Reset your Asrax password"
    body = (
        "Choose a new password for your Asrax account. "
        "If you did not ask for this, you can ignore this message."
    )
    html = _shell(
        preheader="Reset your Asrax password securely.",
        headline="Reset your password",
        body=body,
        cta_label="Reset password",
        cta_url=action_url,
        app_home=app_home,
        show_feature_grid=True,
        feature_compact=True,
        value_line=None,
    )
    return (
        subject,
        html,
        _plain(
            headline=subject,
            body=body,
            action_url=action_url,
            include_features=True,
        ),
    )

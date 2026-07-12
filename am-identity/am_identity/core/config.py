from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IdentitySettings(BaseSettings):
    app_name: str = Field(default="am-identity", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_port: int = Field(default=8080, alias="APP_PORT")

    keycloak_url: str = Field(..., alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(..., alias="KEYCLOAK_REALM")
    keycloak_admin_user: str = Field(..., alias="KEYCLOAK_ADMIN_USER")
    keycloak_admin_password: str = Field(..., alias="KEYCLOAK_ADMIN_PASSWORD")

    oidc_token_url: str = Field(..., alias="OIDC_TOKEN_URL")
    oidc_issuer: str = Field(..., alias="OIDC_ISSUER")
    oidc_jwks_url: str = Field(..., alias="OIDC_JWKS_URL")

    identity_client_id: str = Field(
        default="am-identity-service", alias="AM_IDENTITY_CLIENT_ID"
    )
    identity_client_secret: str = Field(..., alias="AM_IDENTITY_CLIENT_SECRET")
    web_client_id: str = Field(default="am-web-client", alias="AM_WEB_CLIENT_ID")
    google_idp_alias: str = Field(default="google", alias="GOOGLE_IDP_ALIAS")
    google_client_id: str = Field(..., alias="GOOGLE_CLIENT_ID")
    google_state_ttl_seconds: int = Field(default=300, alias="GOOGLE_STATE_TTL_SECONDS")
    allowed_google_redirect_uris: str = Field(
        default="http://localhost:9000/callback,https://am.munish.org/callback,https://am.asrax.in/callback,https://am-dev.asrax.in/callback",
        alias="ALLOWED_GOOGLE_REDIRECT_URIS",
    )

    service_token_ttl: int = Field(default=300, alias="SERVICE_TOKEN_TTL")

    verify_ssl: bool = Field(default=True, alias="IDENTITY_VERIFY_SSL")

    # Branded auth mail (identity-owned; Keycloak is still the user store).
    auth_ui_base_url: str = Field(
        default="https://am.asrax.in", alias="AUTH_UI_BASE_URL"
    )
    auth_email_token_secret: str = Field(
        default="", alias="AUTH_EMAIL_TOKEN_SECRET"
    )
    auth_email_token_ttl_seconds: int = Field(
        default=43200, alias="AUTH_EMAIL_TOKEN_TTL_SECONDS"
    )
    # Prefer SMTP_*; KEYCLOAK_SMTP_* accepted via env aliases in vault sync.
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="", alias="SMTP_FROM")
    smtp_from_display_name: str = Field(
        default="Asrax Accounts", alias="SMTP_FROM_DISPLAY_NAME"
    )
    smtp_ssl: bool = Field(default=True, alias="SMTP_SSL")
    smtp_starttls: bool = Field(default=False, alias="SMTP_STARTTLS")

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    def resolved_smtp(self) -> dict[str, object]:
        """Merge SMTP_* with KEYCLOAK_SMTP_* fallbacks from the environment."""
        import os

        def pick(primary: str, fallback: str, default: str = "") -> str:
            return (os.getenv(primary) or os.getenv(fallback) or default).strip()

        host = pick("SMTP_HOST", "KEYCLOAK_SMTP_HOST", self.smtp_host)
        user = pick("SMTP_USER", "KEYCLOAK_SMTP_USER", self.smtp_user)
        password = pick("SMTP_PASSWORD", "KEYCLOAK_SMTP_PASSWORD", self.smtp_password)
        from_addr = pick("SMTP_FROM", "KEYCLOAK_SMTP_FROM", self.smtp_from or user)
        display = pick(
            "SMTP_FROM_DISPLAY_NAME",
            "KEYCLOAK_SMTP_FROM_DISPLAY_NAME",
            self.smtp_from_display_name,
        )
        port_raw = pick("SMTP_PORT", "KEYCLOAK_SMTP_PORT", str(self.smtp_port))
        ssl_raw = pick("SMTP_SSL", "KEYCLOAK_SMTP_SSL", "true" if self.smtp_ssl else "false")
        starttls_raw = pick(
            "SMTP_STARTTLS",
            "KEYCLOAK_SMTP_STARTTLS",
            "true" if self.smtp_starttls else "false",
        )
        return {
            "host": host,
            "port": int(port_raw or 465),
            "user": user,
            "password": password,
            "from_addr": from_addr,
            "from_display_name": display or "Asrax Accounts",
            "ssl": ssl_raw.lower() in ("1", "true", "yes"),
            "starttls": starttls_raw.lower() in ("1", "true", "yes"),
        }


@lru_cache(maxsize=1)
def get_settings() -> IdentitySettings:
    return IdentitySettings()

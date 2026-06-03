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
    google_state_ttl_seconds: int = Field(default=300, alias="GOOGLE_STATE_TTL_SECONDS")
    allowed_google_redirect_uris: str = Field(
        default="http://localhost:9000/callback,https://am.munish.org/callback,https://am.asrax.in/callback,https://am-dev.asrax.in/callback",
        alias="ALLOWED_GOOGLE_REDIRECT_URIS",
    )

    service_token_ttl: int = Field(default=300, alias="SERVICE_TOKEN_TTL")

    verify_ssl: bool = Field(default=True, alias="IDENTITY_VERIFY_SSL")

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> IdentitySettings:
    return IdentitySettings()

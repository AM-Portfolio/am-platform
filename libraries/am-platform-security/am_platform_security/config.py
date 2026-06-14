from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLATFORM_ROOT = Path(__file__).resolve().parents[3]


class SecuritySettings(BaseSettings):
    auth_disabled: bool = Field(default=False, alias="AUTH_DISABLED")
    oidc_issuer: str = Field(default="http://localhost/disabled", alias="OIDC_ISSUER")
    oidc_jwks_url: str = Field(default="http://localhost/disabled/certs", alias="OIDC_JWKS_URL")
    service_role_name: str = Field(default="service", alias="SERVICE_ROLE_NAME")

    model_config = SettingsConfigDict(
        env_file=(str(PLATFORM_ROOT / ".env"), str(PLATFORM_ROOT / ".secrets.env")),
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_security_settings() -> SecuritySettings:
    return SecuritySettings()

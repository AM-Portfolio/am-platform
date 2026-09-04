from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLATFORM_ROOT = Path(__file__).resolve().parents[3]


class UserPlatformSettings(BaseSettings):
    app_name: str = Field(default="am-user-platform", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_port: int = Field(default=8115, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    user_platform_postgres_host: str | None = Field(
        default=None, alias="AM_USER_PLATFORM_POSTGRES_HOST"
    )
    user_platform_postgres_port: int | None = Field(
        default=None, alias="AM_USER_PLATFORM_POSTGRES_PORT"
    )
    db_name: str = Field(default="user_platform", alias="AM_USER_PLATFORM_DB_NAME")
    db_user: str = Field(
        default="am_user_platform_user", alias="AM_USER_PLATFORM_DB_USER"
    )
    db_password: str = Field(default="", alias="AM_USER_PLATFORM_DB_PASSWORD")
    postgres_ssl: bool = Field(default=False, alias="AM_USER_PLATFORM_POSTGRES_SSL")

    service_token: str = Field(default="", alias="SERVICE_TOKEN")

    model_config = SettingsConfigDict(
        env_file=(str(PLATFORM_ROOT / ".env"), str(PLATFORM_ROOT / ".secrets.env")),
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def effective_postgres_host(self) -> str:
        if self.user_platform_postgres_host:
            return self.user_platform_postgres_host
        return self.postgres_host

    @property
    def effective_postgres_port(self) -> int:
        if self.user_platform_postgres_port is not None:
            return self.user_platform_postgres_port
        return self.postgres_port

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.effective_postgres_host}:{self.effective_postgres_port}/{self.db_name}"
        )

    @property
    def engine_connect_args(self) -> dict[str, bool]:
        return {"ssl": self.postgres_ssl}


@lru_cache(maxsize=1)
def get_settings() -> UserPlatformSettings:
    return UserPlatformSettings()

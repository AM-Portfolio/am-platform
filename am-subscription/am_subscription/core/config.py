from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLATFORM_ROOT = Path(__file__).resolve().parents[3]


class SubscriptionSettings(BaseSettings):
    app_name: str = Field(default="am-subscription", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_port: int = Field(default=8080, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    # Local dev override when POSTGRES_HOST is a cluster DNS name (see am-infra tcp gateway)
    subscription_postgres_host: str | None = Field(
        default=None, alias="AM_SUBSCRIPTION_POSTGRES_HOST"
    )
    subscription_postgres_port: int | None = Field(
        default=None, alias="AM_SUBSCRIPTION_POSTGRES_PORT"
    )
    db_name: str = Field(default="subscription", alias="AM_SUBSCRIPTION_DB_NAME")
    db_user: str = Field(default="am_subscription_user", alias="AM_SUBSCRIPTION_DB_USER")
    db_password: str = Field(default="", alias="AM_SUBSCRIPTION_DB_PASSWORD")
    # VPS TCP gateway (postgres.asrax.in:8891) is plain TCP; asyncpg otherwise tries SSL and fails.
    postgres_ssl: bool = Field(default=False, alias="AM_SUBSCRIPTION_POSTGRES_SSL")

    lago_api_url: str = Field(default="https://lago.munish.org", alias="LAGO_API_URL")
    lago_api_key: str = Field(default="", alias="LAGO_ORG_API_KEY")
    lago_webhook_secret: str = Field(default="", alias="LAGO_WEBHOOK_SECRET")

    default_plan_code: str = Field(default="am_free", alias="DEFAULT_PLAN_CODE")
    plans_config_path: str = Field(
        default=str(PLATFORM_ROOT / "automation" / "helm" / "lago-plans.json"),
        alias="PLANS_CONFIG_PATH",
    )

    kafka_enabled: bool = Field(default=False, alias="KAFKA_ENABLED")
    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")

    model_config = SettingsConfigDict(
        env_file=(str(PLATFORM_ROOT / ".env"), str(PLATFORM_ROOT / ".secrets.env")),
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def effective_postgres_host(self) -> str:
        if self.subscription_postgres_host:
            return self.subscription_postgres_host
        return self.postgres_host

    @property
    def effective_postgres_port(self) -> int:
        if self.subscription_postgres_port is not None:
            return self.subscription_postgres_port
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
def get_settings() -> SubscriptionSettings:
    return SubscriptionSettings()

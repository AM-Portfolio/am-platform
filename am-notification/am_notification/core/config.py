from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

PLATFORM_ROOT = Path(__file__).resolve().parents[3]


class NotificationSettings(BaseSettings):
    app_name: str = Field(default="am-notification", alias="APP_NAME")
    app_env: str = Field(default="dev", alias="APP_ENV")
    app_port: int = Field(default=8080, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    mongo_uri: str = Field(default="", alias="AM_NOTIFICATION_MONGO_URI")
    mongo_database: str = Field(default="notification", alias="AM_NOTIFICATION_MONGO_DATABASE")
    mongo_host: str | None = Field(default=None, alias="AM_NOTIFICATION_MONGO_HOST")
    mongo_port: int | None = Field(default=None, alias="AM_NOTIFICATION_MONGO_PORT")
    mongo_user: str = Field(default="am_notification_user", alias="AM_NOTIFICATION_DB_USER")
    mongo_password: str = Field(default="", alias="AM_NOTIFICATION_DB_PASSWORD")

    notification_provider: str = Field(default="novu", alias="NOTIFICATION_PROVIDER")
    novu_api_url: str = Field(default="https://novu-api.munish.org", alias="NOVU_API_URL")
    novu_api_key: str = Field(default="", alias="NOVU_API_KEY")
    novu_app_id: str = Field(default="am-platform", alias="NOVU_APPLICATION_IDENTIFIER")

    kafka_enabled: bool = Field(default=False, alias="KAFKA_ENABLED")
    kafka_bootstrap_servers: str = Field(
        default="kafka.infra.svc.cluster.local:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_bootstrap_servers_override: str | None = Field(
        default=None, alias="AM_NOTIFICATION_KAFKA_BOOTSTRAP_SERVERS"
    )
    kafka_security_protocol: str = Field(default="SASL_PLAINTEXT", alias="KAFKA_SECURITY_PROTOCOL")
    kafka_sasl_mechanism: str = Field(default="SCRAM-SHA-256", alias="KAFKA_SASL_MECHANISM")
    kafka_username: str = Field(default="", alias="KAFKA_USERNAME")
    kafka_password: str = Field(default="", alias="KAFKA_PASSWORD")
    kafka_group_id: str = Field(default="am-notification-consumer", alias="KAFKA_NOTIFICATION_GROUP_ID")

    kafka_topics: str = Field(
        default="am.identity.events.v1,am.subscription.events.v1,am.usage.events.v1,am.notification.commands.v1",
        alias="KAFKA_NOTIFICATION_TOPICS",
    )
    kafka_events_topic: str = Field(default="am.notification.events.v1", alias="KAFKA_NOTIFICATION_EVENTS_TOPIC")
    kafka_dlq_topic: str = Field(
        default="am.notification.commands.dlq.v1", alias="KAFKA_NOTIFICATION_DLQ_TOPIC"
    )

    model_config = SettingsConfigDict(
        env_file=(str(PLATFORM_ROOT / ".env"), str(PLATFORM_ROOT / ".secrets.env")),
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def effective_kafka_bootstrap(self) -> str:
        if self.kafka_bootstrap_servers_override:
            return self.kafka_bootstrap_servers_override
        return self.kafka_bootstrap_servers

    @property
    def kafka_topic_list(self) -> list[str]:
        return [topic.strip() for topic in self.kafka_topics.split(",") if topic.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_mongo_uri(self) -> str:
        if self.mongo_uri and not self.mongo_uri.startswith("<"):
            return self.mongo_uri
        host = self.mongo_host or "mongodb.asrax.in"
        port = self.mongo_port or 8888
        password = self.mongo_password
        return (
            f"mongodb://{self.mongo_user}:{password}@{host}:{port}/"
            f"{self.mongo_database}?authSource={self.mongo_database}&directConnection=true"
        )


@lru_cache(maxsize=1)
def get_settings() -> NotificationSettings:
    return NotificationSettings()

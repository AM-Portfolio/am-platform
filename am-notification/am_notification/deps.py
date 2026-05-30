from functools import lru_cache

from am_notification.core.config import get_settings
from am_notification.core.database import get_database
from am_notification.providers.interface import INotificationProvider
from am_notification.providers.novu_provider import NovuProvider
from am_notification.services.kafka_consumer import NotificationKafkaConsumer
from am_notification.services.notification_service import NotificationService
from am_notification.services.preference_service import PreferenceService


@lru_cache(maxsize=1)
def get_provider() -> INotificationProvider:
    settings = get_settings()
    if settings.notification_provider.lower() == "novu":
        return NovuProvider(settings)
    raise RuntimeError(f"Unsupported notification provider: {settings.notification_provider}")


def get_notification_service() -> NotificationService:
    return NotificationService(get_database(), get_provider())


def get_preference_service() -> PreferenceService:
    return PreferenceService(get_database())


@lru_cache(maxsize=1)
def get_kafka_consumer() -> NotificationKafkaConsumer:
    settings = get_settings()
    return NotificationKafkaConsumer(settings, NotificationService(get_database(), get_provider()))

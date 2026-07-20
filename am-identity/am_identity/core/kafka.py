import json
import logging
from aiokafka import AIOKafkaProducer
from aiokafka.helpers import create_ssl_context
from am_identity.core.config import get_settings

logger = logging.getLogger(__name__)


async def publish_event(topic: str, event_type: str, payload: dict) -> None:
    settings = get_settings()
    if not settings.kafka_enabled:
        logger.info(f"Kafka is disabled. Skipping event {event_type} on {topic}")
        return

    kwargs = {
        "bootstrap_servers": settings.kafka_bootstrap_servers,
        "security_protocol": settings.kafka_security_protocol,
    }
    if settings.kafka_username and settings.kafka_password:
        kwargs["sasl_mechanism"] = settings.kafka_sasl_mechanism
        kwargs["sasl_plain_username"] = settings.kafka_username
        kwargs["sasl_plain_password"] = settings.kafka_password
    if settings.kafka_security_protocol.endswith("SSL"):
        kwargs["ssl_context"] = create_ssl_context()

    try:
        producer = AIOKafkaProducer(**kwargs)
        await producer.start()
        try:
            envelope = {"type": event_type, "data": payload}
            message_bytes = json.dumps(envelope).encode("utf-8")
            await producer.send_and_wait(topic, message_bytes)
            logger.info(f"Published event {event_type} to topic {topic}")
        finally:
            await producer.stop()
    except Exception as e:
        logger.error(f"Failed to publish event {event_type} to topic {topic}: {e}")

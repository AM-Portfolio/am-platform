"""Identity Kafka helpers — ADR-003 EventEnvelope on am.identity.events.v1."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from aiokafka import AIOKafkaProducer
from aiokafka.helpers import create_ssl_context
from am_platform_common import EventEnvelope

from am_identity.core.config import get_settings

logger = logging.getLogger(__name__)

IDENTITY_EVENTS_TOPIC = "am.identity.events.v1"
EVENT_USER_REGISTERED = "am.identity.user_registered.v1"
EVENT_EMAIL_VERIFIED = "am.identity.email_verified.v1"

# Keycloak user attributes (must be registered on realm user profile).
ATTR_REFERRAL_CODE = "asraxReferralCode"
ATTR_DEVICE_ID = "asraxDeviceId"
ATTR_USER_REGISTERED_EVENT = "asraxUserRegisteredEventSent"
ATTR_EMAIL_VERIFIED_EVENT = "asraxEmailVerifiedEventSent"


def normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_referral_code(value: str | None) -> str | None:
    """Opaque invite code — strip + upper; identity does not validate existence."""
    cleaned = normalize_optional_str(value)
    return cleaned.upper() if cleaned else None


def signup_attribution_payload(
    *,
    user_id: str,
    email: str,
    referral_code: str | None = None,
    device_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "email": email,
    }
    code = normalize_referral_code(referral_code)
    device = normalize_optional_str(device_id)
    if code is not None:
        payload["referral_code"] = code
    if device is not None:
        payload["device_id"] = device
    return payload


async def publish_event(
    topic: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    user_id: str | None = None,
    correlation_id: str | None = None,
    idempotency_key: str | None = None,
    tenant_id: str = "default",
) -> None:
    """Publish an ADR-003 EventEnvelope (also readable as legacy type/data via event_type/payload)."""
    settings = get_settings()
    envelope = EventEnvelope(
        event_type=event_type,
        producer=settings.app_name,
        tenant_id=tenant_id,
        user_id=user_id,
        correlation_id=correlation_id or str(uuid4()),
        idempotency_key=idempotency_key
        or f"{event_type}:{user_id or 'unknown'}",
        payload=payload,
    )
    if not settings.kafka_enabled:
        logger.info(
            "Kafka disabled; skipping event %s on %s (event_id=%s)",
            event_type,
            topic,
            envelope.event_id,
        )
        return

    kwargs: dict[str, Any] = {
        "bootstrap_servers": settings.kafka_bootstrap_servers,
        "security_protocol": settings.kafka_security_protocol,
    }
    if settings.kafka_username and settings.kafka_password:
        kwargs["sasl_mechanism"] = settings.kafka_sasl_mechanism
        kwargs["sasl_plain_username"] = settings.kafka_username
        kwargs["sasl_plain_password"] = settings.kafka_password
    if settings.kafka_security_protocol.endswith("SSL"):
        kwargs["ssl_context"] = create_ssl_context()

    import asyncio

    message_bytes = envelope.model_dump_json().encode("utf-8")
    max_retries = 3
    retry_delay = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            producer = AIOKafkaProducer(**kwargs)
            await producer.start()
            try:
                await producer.send_and_wait(topic, message_bytes)
                logger.info(
                    "Published event %s to topic %s (event_id=%s)",
                    event_type,
                    topic,
                    envelope.event_id,
                )
                return
            finally:
                await producer.stop()
        except Exception as e:
            if attempt == max_retries:
                logger.error(
                    "Failed to publish event %s to topic %s after %s attempts: %s",
                    event_type,
                    topic,
                    max_retries,
                    e,
                )
            else:
                logger.warning(
                    "Failed to publish event %s (attempt %s/%s): %s. Retrying in %ss...",
                    event_type,
                    attempt,
                    max_retries,
                    e,
                    retry_delay,
                )
                await asyncio.sleep(retry_delay)
                retry_delay *= 2


async def publish_user_registered(
    *,
    user_id: str,
    email: str,
    referral_code: str | None = None,
    device_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    payload = signup_attribution_payload(
        user_id=user_id,
        email=email,
        referral_code=referral_code,
        device_id=device_id,
    )
    await publish_event(
        IDENTITY_EVENTS_TOPIC,
        EVENT_USER_REGISTERED,
        payload,
        user_id=user_id,
        correlation_id=correlation_id,
        idempotency_key=f"user-registered:{user_id}",
    )


async def publish_email_verified(
    *,
    user_id: str,
    email: str,
    referral_code: str | None = None,
    device_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    """Emit once per user (caller must enforce once-only). Repeats referral fields for L8."""
    payload = signup_attribution_payload(
        user_id=user_id,
        email=email,
        referral_code=referral_code,
        device_id=device_id,
    )
    await publish_event(
        IDENTITY_EVENTS_TOPIC,
        EVENT_EMAIL_VERIFIED,
        payload,
        user_id=user_id,
        correlation_id=correlation_id,
        idempotency_key=f"email-verified:{user_id}",
    )


def envelope_from_json(raw: bytes | str) -> dict[str, Any]:
    """Test helper — parse published JSON."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("envelope must be an object")
    return data

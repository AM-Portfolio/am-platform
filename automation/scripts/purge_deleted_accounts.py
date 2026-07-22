import asyncio
import os
import json
import logging
from datetime import datetime, timezone

import httpx
from aiokafka import AIOKafkaProducer

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("purge_accounts")

async def get_admin_token(client: httpx.AsyncClient, keycloak_url: str, admin_user: str, admin_password: str) -> str:
    url = f"{keycloak_url}/realms/master/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": admin_user,
        "password": admin_password,
    }
    response = await client.post(url, data=data)
    response.raise_for_status()
    return response.json()["access_token"]


async def main():
    keycloak_url = os.environ.get("KEYCLOAK_URL", "http://keycloak.infra.svc.cluster.local:8080").rstrip("/")
    keycloak_realm = os.environ.get("KEYCLOAK_REALM", "am")
    admin_user = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
    admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
    verify_ssl = os.environ.get("IDENTITY_VERIFY_SSL", "true").lower() in ("1", "true", "yes")
    kafka_bootstrap_servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka.infra.svc.cluster.local:9092")
    kafka_topic = "am.identity.events.v1"
    purge_enabled = os.environ.get("PURGE_ENABLED", "true").lower() in ("true", "1", "yes")

    purge_period_minutes = os.environ.get("PURGE_PERIOD_MINUTES")
    if purge_period_minutes:
        ninety_days_seconds = int(purge_period_minutes) * 60
    else:
        purge_period_days = int(os.environ.get("PURGE_PERIOD_DAYS", "90"))
        ninety_days_seconds = purge_period_days * 24 * 60 * 60

    if not admin_password:
        logger.error("KEYCLOAK_ADMIN_PASSWORD is required")
        return

    logger.info("Starting purge deleted accounts cron job...")
    now_ts = datetime.now(timezone.utc).timestamp()

    kafka_enabled = os.environ.get("KAFKA_ENABLED", "false").lower() in ("true", "1", "yes")
    producer = None
    if kafka_enabled:
        try:
            logger.info("Kafka integration enabled. Initializing AIOKafkaProducer...")
            kafka_kwargs = {
                "bootstrap_servers": kafka_bootstrap_servers,
                "security_protocol": os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT"),
            }
            kafka_user = os.environ.get("KAFKA_USERNAME")
            kafka_pass = os.environ.get("KAFKA_PASSWORD")
            if kafka_user and kafka_pass:
                kafka_kwargs["sasl_mechanism"] = os.environ.get("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256")
                kafka_kwargs["sasl_plain_username"] = kafka_user
                kafka_kwargs["sasl_plain_password"] = kafka_pass
            if kafka_kwargs["security_protocol"].endswith("SSL"):
                from aiokafka.helpers import create_ssl_context
                kafka_kwargs["ssl_context"] = create_ssl_context()
                
            producer = AIOKafkaProducer(**kafka_kwargs)
            await producer.start()
            logger.info("Kafka producer started successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}. Events will not be published.")
            producer = None
    else:
        logger.info("Kafka integration disabled. Events will not be published.")

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=verify_ssl) as client:
            admin_token = await get_admin_token(client, keycloak_url, admin_user, admin_password)
            headers = {"Authorization": f"Bearer {admin_token}"}
            users_url = f"{keycloak_url}/admin/realms/{keycloak_realm}/users"

            # Fetch all users (might need pagination for very large realms)
            response = await client.get(
                users_url, params={"max": 1000}, headers=headers
            )
            response.raise_for_status()
            users = response.json()

            purged_count = 0
            for user in users:
                attrs = user.get("attributes", {})

                # Check for pending deletion
                if attrs.get("account_status") == ["pending_deletion"]:
                    req_at = attrs.get("deletion_requested_at")

                    if not req_at:
                        continue

                    req_ts = float(req_at[0])

                    # If retention period has passed
                    if now_ts - req_ts >= ninety_days_seconds:
                        user_id = user["id"]
                        email = user.get("email", user.get("username", ""))
                        feedback = attrs.get("deletion_feedback", [""])[0]

                        if not purge_enabled:
                            logger.info(f"[DRY-RUN] Would purge user: {user_id} (Feedback: {feedback})")
                            purged_count += 1
                            continue

                        logger.info(f"Purging user: {user_id} (Feedback: {feedback})")

                        # Hard delete from Keycloak
                        del_resp = await client.delete(
                            f"{users_url}/{user_id}", headers=headers
                        )
                        del_resp.raise_for_status()

                        # Emit Kafka Event for other services if producer is available
                        if producer:
                            try:
                                event_payload = {
                                    "type": "user.permanently_deleted.v1",
                                    "data": {"user_id": user_id, "email": email},
                                }
                                await producer.send_and_wait(
                                    kafka_topic, json.dumps(event_payload).encode("utf-8")
                                )
                                logger.info(f"Published deletion event to Kafka for user: {user_id}")
                            except Exception as e:
                                logger.error(f"Failed to publish Kafka event for user {user_id}: {e}")
                        else:
                            logger.info(f"Kafka disabled/offline. Skipped event publishing for: {user_id}")
                        purged_count += 1

            if not purge_enabled:
                logger.info(f"Purge dry-run complete. Would have hard deleted {purged_count} accounts.")
            else:
                logger.info(f"Purge complete. Hard deleted {purged_count} accounts.")

    finally:
        if producer:
            await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())

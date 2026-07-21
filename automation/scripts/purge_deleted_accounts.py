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

KEYCLOAK_URL = os.environ.get(
    "KEYCLOAK_URL", "http://keycloak.infra.svc.cluster.local:8080"
).rstrip("/")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "am")
ADMIN_USER = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
VERIFY_SSL = os.environ.get("IDENTITY_VERIFY_SSL", "true").lower() in (
    "1",
    "true",
    "yes",
)

KAFKA_BOOTSTRAP_SERVERS = os.environ.get(
    "KAFKA_BOOTSTRAP_SERVERS", "kafka.infra.svc.cluster.local:9092"
)
KAFKA_TOPIC = "am.identity.events.v1"

# 1. Feature Flag to turn the purge on/off (defaults to True)
PURGE_ENABLED = os.environ.get("PURGE_ENABLED", "true").lower() in ("true", "1", "yes")

# 2. Deletion Period (configurable, defaults to 90 days)
PURGE_PERIOD_DAYS = int(os.environ.get("PURGE_PERIOD_DAYS", "90"))
NINETY_DAYS_SECONDS = PURGE_PERIOD_DAYS * 24 * 60 * 60


async def get_admin_token(client: httpx.AsyncClient) -> str:
    url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    data = {
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASSWORD,
    }
    response = await client.post(url, data=data)
    response.raise_for_status()
    return response.json()["access_token"]


async def main():
    if not ADMIN_PASSWORD:
        logger.error("KEYCLOAK_ADMIN_PASSWORD is required")
        return

    logger.info("Starting purge deleted accounts cron job...")
    now_ts = datetime.now(timezone.utc).timestamp()

    producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    await producer.start()

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=VERIFY_SSL) as client:
            admin_token = await get_admin_token(client)
            headers = {"Authorization": f"Bearer {admin_token}"}
            users_url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"

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

                    # If 90 days have passed
                    if now_ts - req_ts >= NINETY_DAYS_SECONDS:
                        user_id = user["id"]
                        email = user.get("email", user.get("username", ""))
                        feedback = attrs.get("deletion_feedback", [""])[0]

                        if not PURGE_ENABLED:
                            logger.info(f"[DRY-RUN] Would purge user: {user_id} (Feedback: {feedback})")
                            purged_count += 1
                            continue

                        logger.info(f"Purging user: {user_id} (Feedback: {feedback})")

                        # Hard delete from Keycloak
                        del_resp = await client.delete(
                            f"{users_url}/{user_id}", headers=headers
                        )
                        del_resp.raise_for_status()

                        # Emit Kafka Event for other services
                        event_payload = {
                            "type": "user.permanently_deleted.v1",
                            "data": {"user_id": user_id, "email": email},
                        }
                        await producer.send_and_wait(
                            KAFKA_TOPIC, json.dumps(event_payload).encode("utf-8")
                        )
                        purged_count += 1

            if not PURGE_ENABLED:
                logger.info(f"Purge dry-run complete. Would have hard deleted {purged_count} accounts.")
            else:
                logger.info(f"Purge complete. Hard deleted {purged_count} accounts.")

    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())

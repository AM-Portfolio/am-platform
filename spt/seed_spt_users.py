import os
import httpx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("seed_spt")

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

async def create_user(client: httpx.AsyncClient, keycloak_url: str, realm: str, token: str, username: str, email: str) -> None:
    url = f"{keycloak_url}/admin/realms/{realm}/users"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    user_payload = {
        "username": username,
        "email": email,
        "enabled": True,
        "emailVerified": True,
        "credentials": [
            {
                "type": "password",
                "value": "SptPassword.1",
                "temporary": False
            }
        ]
    }
    response = await client.post(url, headers=headers, json=user_payload)
    if response.status_code == 201:
        logger.info(f"Successfully created user: {username}")
    elif response.status_code == 409:
        logger.info(f"User {username} already exists (skipping)")
    else:
        logger.error(f"Failed to create user {username}: {response.status_code} - {response.text}")

async def main():
    keycloak_url = os.environ.get("KEYCLOAK_URL", "http://localhost:9080").rstrip("/")
    realm = os.environ.get("KEYCLOAK_REALM", "am")
    admin_user = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
    admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
    verify_ssl = os.environ.get("IDENTITY_VERIFY_SSL", "false").lower() in ("1", "true", "yes")

    num_users = 100

    logger.info("Initializing Keycloak seeding for SPT...")
    async with httpx.AsyncClient(verify=verify_ssl) as client:
        try:
            token = await get_admin_token(client, keycloak_url, admin_user, admin_password)
            logger.info("Obtained admin token from Keycloak.")
        except Exception as e:
            logger.error(f"Failed to obtain admin token: {e}")
            return

        for i in range(1, num_users + 1):
            username = f"spt-user-{i}"
            email = f"spt-user-{i}@example.com"
            try:
                await create_user(client, keycloak_url, realm, token, username, email)
            except Exception as e:
                logger.error(f"Failed to seed user {username}: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

import time
import logging
from typing import Dict, Any, Optional
import httpx
from jwt.algorithms import RSAAlgorithm
from app.config import settings

logger = logging.getLogger(__name__)

class JWKSCache:
    def __init__(self, jwks_url: str, cache_ttl: int = 300):
        self.jwks_url = jwks_url
        self.cache_ttl = cache_ttl
        self._keys: Dict[str, Any] = {}
        self._last_fetched: float = 0.0

    async def _fetch_jwks(self) -> None:
        """Fetch JWKS keys from Keycloak certificates URL and parse them."""
        now = time.time()
        # If cache is still valid and we have keys, skip fetching
        if self._keys and (now - self._last_fetched) < self.cache_ttl:
            return

        logger.info(f"Fetching JWKS from Keycloak: {self.jwks_url}")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.jwks_url)
                response.raise_for_status()
                jwks = response.json()
                
                new_keys = {}
                for key_data in jwks.get("keys", []):
                    kid = key_data.get("kid")
                    if kid:
                        # Convert JWK to a PEM public key object (or PyJWT compatible public key)
                        public_key = RSAAlgorithm.from_jwk(key_data)
                        new_keys[kid] = public_key
                
                self._keys = new_keys
                self._last_fetched = now
                logger.info(f"Successfully loaded {len(self._keys)} public keys from JWKS.")
        except Exception as e:
            logger.error(f"Failed to fetch JWKS keys from Keycloak: {str(e)}")
            # If fetch fails, keep using old keys if we have them
            if not self._keys:
                raise e

    async def get_public_key(self, kid: str) -> Any:
        """Retrieves matching PEM key for the given key ID (kid)."""
        await self._fetch_jwks()
        
        if kid not in self._keys:
            # Force refresh cache once if kid not found, just in case Keycloak rolled keys
            logger.warning(f"Key ID {kid} not found in cache. Refreshing JWKS...")
            self._last_fetched = 0.0  # bypass TTL check
            await self._fetch_jwks()

        if kid not in self._keys:
            raise KeyError(f"Key ID {kid} not found in Keycloak JWKS")
            
        return self._keys[kid]

# Global singleton JWKS Cache
jwks_cache = JWKSCache(jwks_url=settings.OIDC_JWKS_URL, cache_ttl=settings.OIDC_JWKS_CACHE_TTL_SECONDS)

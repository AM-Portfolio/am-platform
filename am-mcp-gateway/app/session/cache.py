import hashlib
import logging
from typing import Optional
import redis
from app.config import settings

logger = logging.getLogger(__name__)

# List of keywords indicating dynamic data that should NOT be cached
DYNAMIC_KEYWORDS = {"now", "today", "current", "latest", "realtime", "live", "price", "valuation"}

class ResponseCache:
    def __init__(self):
        self.enabled = settings.CACHE_ENABLED
        self.redis_client = None
        self.in_memory_cache = {}

        if self.enabled and settings.CACHE_BACKEND == "redis":
            try:
                logger.info(f"Initializing Redis Cache with URL: {settings.REDIS_URL}")
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0
                )
                # Test connection
                self.redis_client.ping()
                logger.info("Successfully connected to Redis cache backend.")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis, falling back to in-memory cache: {e}")
                self.redis_client = None

    def _should_cache(self, prompt: str) -> bool:
        """Determines if a prompt should be cached based on the presence of dynamic keywords."""
        sanitized = prompt.lower().split()
        for word in sanitized:
            # Check prefix/substring match for keywords like 'today', 'latest'
            for kw in DYNAMIC_KEYWORDS:
                if kw in word:
                    logger.info(f"Prompt matches dynamic keyword '{kw}'. Skipping caching.")
                    return False
        return True

    def build_key(self, user_id: str, prompt: str, model: str) -> str:
        sanitized = prompt.strip().lower()
        h = hashlib.sha256(f"{user_id}:{sanitized}:{model}".encode()).hexdigest()
        return f"mcp:cache:{h}"

    async def get(self, user_id: str, prompt: str, model: str) -> Optional[str]:
        if not self.enabled:
            return None

        if not self._should_cache(prompt):
            return None

        key = self.build_key(user_id, prompt, model)
        try:
            if self.redis_client:
                return self.redis_client.get(key)
            else:
                return self.in_memory_cache.get(key)
        except Exception as e:
            logger.error(f"Error reading from response cache: {e}")
            return None

    async def set(self, user_id: str, prompt: str, model: str, value: str, ttl: Optional[int] = None) -> None:
        if not self.enabled:
            return

        if not self._should_cache(prompt):
            return

        key = self.build_key(user_id, prompt, model)
        ttl = ttl or settings.CACHE_TTL_SECONDS
        try:
            if self.redis_client:
                self.redis_client.set(key, value, ex=ttl)
            else:
                self.in_memory_cache[key] = value
                # Note: Simple in-memory cache does not enforce TTL in this mockup but is fine for fallback
        except Exception as e:
            logger.error(f"Error writing to response cache: {e}")

response_cache = ResponseCache()

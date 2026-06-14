from fastapi import APIRouter, status
from app.session.cache import response_cache

router = APIRouter()

@router.get("/health", status_code=status.HTTP_200_OK)
async def health():
    """Liveness probe."""
    return {"status": "ok", "service": "am-mcp-gateway"}

@router.get("/ready", status_code=status.HTTP_200_OK)
async def ready():
    """Readiness probe."""
    cache_status = "disabled"
    if response_cache.enabled:
        if response_cache.redis_client:
            try:
                response_cache.redis_client.ping()
                cache_status = "connected"
            except Exception:
                cache_status = "disconnected"
        else:
            cache_status = "in_memory"

    return {
        "status": "ready",
        "cache_backend": cache_status
    }

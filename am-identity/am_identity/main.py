from fastapi import FastAPI

from am_identity.api.admin_router import router as admin_router
from am_identity.api.auth_router import router as auth_router
from am_identity.api.internal_router import router as internal_router
from am_identity.api.user_router import router as user_router
from am_identity.core.config import get_settings
from am_platform_common import LoggingMiddleware, setup_logging

settings = get_settings()
setup_logging(env=settings.app_env)

app = FastAPI(
    title="AM Identity Service",
    version="0.1.0",
    description="Unified Keycloak-backed identity layer for AM Platform",
)
app.add_middleware(LoggingMiddleware)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(admin_router)
app.include_router(internal_router)

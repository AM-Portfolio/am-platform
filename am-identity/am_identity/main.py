from fastapi import FastAPI

from am_identity.api.admin_router import router as admin_router
from am_identity.api.auth_router import router as auth_router
from am_identity.api.bff_router import router as bff_router
from am_identity.api.device_link_router import router as device_link_router
from am_identity.api.internal_router import router as internal_router
from am_identity.api.step_up_router import router as step_up_router
from am_identity.api.user_router import router as user_router
from am_identity.api.web_otp_router import router as web_otp_router
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
app.include_router(device_link_router)
app.include_router(web_otp_router)
app.include_router(step_up_router)
app.include_router(bff_router)
app.include_router(user_router)
app.include_router(admin_router)
app.include_router(internal_router)

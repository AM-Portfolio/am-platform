from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from am_notification.api.internal_router import router as internal_router
from am_notification.api.notification_router import router as notification_router
from am_notification.api.preference_router import router as preference_router
from am_notification.api.webhook_router import router as webhook_router
from am_notification.core.config import get_settings
from am_notification.core.database import close_db, init_db, ping_db
from am_notification.core.log_utils import get_logger
from am_notification.deps import get_kafka_consumer, get_provider
from am_platform_common import (
    APIException,
    InternalServerError,
    LoggingMiddleware,
    setup_logging,
)

settings = get_settings()
setup_logging(env=settings.app_env, level=settings.log_level)
logger = get_logger("main")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info(
        "Starting am-notification",
        extra={
            "port": settings.app_port,
            "provider": settings.notification_provider,
            "kafka_enabled": settings.kafka_enabled,
        },
    )
    await init_db()
    consumer = get_kafka_consumer()
    await consumer.start()
    yield
    await consumer.stop()
    await close_db()
    logger.info("Shutting down am-notification")


app = FastAPI(
    title="AM Notification Service",
    version="0.1.0",
    description="Lean notification orchestration with Novu adapter",
    lifespan=lifespan,
)
app.add_middleware(LoggingMiddleware)


def _request_context(request: Request) -> dict[str, str]:
    return {"http_method": request.method, "http_path": request.url.path}


@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error(
            exc.message,
            extra={**_request_context(request), "error_code": exc.error_code},
        )
    else:
        logger.warning(
            exc.message,
            extra={**_request_context(request), "error_code": exc.error_code},
        )
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", extra=_request_context(request))
    message = (
        str(exc)
        if settings.app_env.lower() in ("dev", "local")
        else "Internal server error"
    )
    body = InternalServerError(message=message, error_code="INTERNAL_SERVER_ERROR")
    return JSONResponse(status_code=body.status_code, content=body.to_dict())


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/health/ready")
async def health_ready() -> dict[str, object]:
    mongo_ok = await ping_db(settings)
    provider_ok = await get_provider().health_check()
    ready = mongo_ok and (provider_ok or not settings.novu_api_key)
    return {
        "status": "ok" if ready else "degraded",
        "mongo": mongo_ok,
        "provider": provider_ok,
    }


app.include_router(notification_router)
app.include_router(preference_router)
app.include_router(internal_router)
app.include_router(webhook_router)

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from am_user_platform.modules.ai.api.internal_router import router as internal_ai_router
from am_user_platform.modules.ai.api.session_router import router as session_ai_router
from am_user_platform.core.config import get_settings
from am_user_platform.core.database import close_db, init_db, ping_db
from am_user_platform.core.log_utils import get_logger
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
        "Starting am-user-platform",
        extra={"port": settings.app_port, "env": settings.app_env},
    )
    try:
        await init_db()
    except Exception:
        logger.exception(
            "Database init failed — health will report degraded until Postgres is available"
        )
    yield
    await close_db()
    logger.info("Shutting down am-user-platform")


app = FastAPI(
    title="AM User Platform Service",
    version="0.1.0",
    description="User-facing platform state — AI chat memory (ai module), preferences, corp",
    lifespan=lifespan,
)
app.add_middleware(LoggingMiddleware)


def _request_context(request: Request) -> dict[str, str]:
    return {
        "http_method": request.method,
        "http_path": request.url.path,
    }


@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error(
            exc.message,
            extra={
                **_request_context(request),
                "error_code": exc.error_code,
                "details": exc.details,
            },
        )
    else:
        logger.warning(
            exc.message,
            extra={
                **_request_context(request),
                "error_code": exc.error_code,
                "details": exc.details,
            },
        )
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.exception("Database error", extra=_request_context(request))
    body = InternalServerError(
        message="Database operation failed",
        error_code="DATABASE_ERROR",
        details={"type": type(exc).__name__},
    )
    return JSONResponse(status_code=body.status_code, content=body.to_dict())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception",
        extra={**_request_context(request), "exception_type": type(exc).__name__},
    )
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


@app.get("/ready")
async def ready() -> dict[str, object]:
    db_ok = await ping_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": settings.app_name,
        "database": db_ok,
    }


app.include_router(session_ai_router)
app.include_router(internal_ai_router)

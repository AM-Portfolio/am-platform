from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from am_platform_common.logging import setup_logging
from am_platform_common.middleware import LoggingMiddleware
from am_platform_common.errors import APIException

def install_common(app: FastAPI):
    """
    Auto-wires common platform components into a FastAPI application.
    This mimics Java's @AutoConfiguration by abstracting the boilerplate.
    """
    # 1. Setup global logging format
    setup_logging()
    
    # 2. Add correlation ID and request logging middleware
    app.add_middleware(LoggingMiddleware)
    
    # 3. Register standard exception handlers
    @app.exception_handler(APIException)
    async def api_exception_handler(request, exc: APIException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict()
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error_code": "HTTP_ERROR", "message": str(exc.detail)}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": exc.errors()
            }
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc: Exception):
        import logging
        logging.getLogger("am_platform_common.errors").error(f"Unhandled exception: {exc}", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"error_code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred"}
        )

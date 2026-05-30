import logging
import time
from uuid import uuid4
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from am_platform_common.logging import set_correlation_id, clear_correlation_id

logger = logging.getLogger("am_platform_common.middleware")

class LoggingMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware to trace incoming requests, configure correlation IDs, and log execution details."""
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract existing trace ID or generate a new one
        trace_id = request.headers.get("X-Trace-ID") or request.headers.get("X-Correlation-ID") or str(uuid4())
        span_id = str(uuid4())
        
        # Bind correlation context to the thread/coroutine contextvar
        set_correlation_id(trace_id, span_id)
        
        start_time = time.perf_counter()
        
        # Log incoming request
        logger.info(
            f"Incoming Request: {request.method} {request.url.path}",
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "client_ip": request.client.host if request.client else "unknown",
                "query_params": dict(request.query_params),
            }
        )
        
        try:
            response: Response = await call_next(request)
            
            # Log outgoing response
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                f"Outgoing Response: {request.method} {request.url.path} - Status: {response.status_code} ({duration_ms:.2f}ms)",
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                }
            )
            
            # Inject trace IDs back to client response headers
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Span-ID"] = span_id
            return response
            
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Request Failed: {request.method} {request.url.path} - {type(exc).__name__}: {str(exc)} ({duration_ms:.2f}ms)",
                exc_info=True,
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": duration_ms,
                }
            )
            raise exc
            
        finally:
            # Clear context variables to prevent leakage
            clear_correlation_id()

import logging
import time
from uuid import uuid4
import httpx
from am_platform_common.logging import get_correlation_context

logger = logging.getLogger("am_platform_common.http_client")

def log_request_hook(request: httpx.Request) -> None:
    """Pre-request hook to inject tracing headers and record start time."""
    context = get_correlation_context()
    
    # Propagate trace ID if active in correlation context
    if context["trace_id"]:
        request.headers["X-Trace-ID"] = context["trace_id"]
        
    outgoing_span = str(uuid4())
    request.headers["X-Span-ID"] = outgoing_span
    
    # Store timing context on the request object itself
    request.start_time = time.perf_counter() # type: ignore
    
    logger.info(
        f"Outgoing API Request: {request.method} {request.url}",
        extra={
            "http_method": request.method,
            "http_url": str(request.url),
            "trace_id": context["trace_id"],
            "span_id": outgoing_span,
        }
    )

def log_response_hook(response: httpx.Response) -> None:
    """Post-response hook to log API call results and elapsed time."""
    request = response.request
    start_time = getattr(request, "start_time", None)
    duration_ms = None
    if start_time is not None:
        duration_ms = (time.perf_counter() - start_time) * 1000
        
    duration_str = f" ({duration_ms:.2f}ms)" if duration_ms is not None else ""
    
    logger.info(
        f"Outgoing API Response: {request.method} {request.url} - Status: {response.status_code}{duration_str}",
        extra={
            "http_method": request.method,
            "http_url": str(request.url),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }
    )

def create_async_client(*args, **kwargs) -> httpx.AsyncClient:
    """Create an httpx.AsyncClient with pre-configured logging hooks."""
    event_hooks = kwargs.get("event_hooks") or {}
    
    req_hooks = event_hooks.get("request") or []
    req_hooks.append(log_request_hook)
    event_hooks["request"] = req_hooks
    
    resp_hooks = event_hooks.get("response") or []
    resp_hooks.append(log_response_hook)
    event_hooks["response"] = resp_hooks
    
    kwargs["event_hooks"] = event_hooks
    return httpx.AsyncClient(*args, **kwargs)

def create_sync_client(*args, **kwargs) -> httpx.Client:
    """Create an httpx.Client with pre-configured logging hooks."""
    event_hooks = kwargs.get("event_hooks") or {}
    
    req_hooks = event_hooks.get("request") or []
    req_hooks.append(log_request_hook)
    event_hooks["request"] = req_hooks
    
    resp_hooks = event_hooks.get("response") or []
    resp_hooks.append(log_response_hook)
    event_hooks["response"] = resp_hooks
    
    kwargs["event_hooks"] = event_hooks
    return httpx.Client(*args, **kwargs)

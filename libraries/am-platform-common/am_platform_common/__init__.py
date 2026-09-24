from am_platform_common.logging import (
    setup_logging,
    set_correlation_id,
    clear_correlation_id,
    get_correlation_context,
)
from am_platform_common.errors import (
    APIException,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    NotFoundError,
    ConflictError,
    QuotaExceededError,
    InternalServerError,
)
from am_platform_common.models import (
    BaseDTO,
    APIResponse,
    PaginatedResponse,
    APIErrorResponse,
    EventEnvelope,
)
from am_platform_common.middleware import LoggingMiddleware
from am_platform_common.http_client import create_async_client, create_sync_client
from am_platform_common.plane_a import domain_counter, inc_domain, setup_plane_a

__all__ = [
    # Logging
    "setup_logging",
    "set_correlation_id",
    "clear_correlation_id",
    "get_correlation_context",
    
    # Exceptions
    "APIException",
    "BadRequestError",
    "UnauthorizedError",
    "ForbiddenError",
    "NotFoundError",
    "ConflictError",
    "QuotaExceededError",
    "InternalServerError",
    
    # Models / DTOs
    "BaseDTO",
    "APIResponse",
    "PaginatedResponse",
    "APIErrorResponse",
    "EventEnvelope",
    
    # Middleware & HTTP Clients
    "LoggingMiddleware",
    "create_async_client",
    "create_sync_client",
    # Plane A metrics (observability.yaml)
    "setup_plane_a",
    "inc_domain",
    "domain_counter",
]

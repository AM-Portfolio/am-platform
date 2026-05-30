from typing import Any, Dict, Optional

class APIException(Exception):
    """Base exception class for all platform APIs."""
    status_code: int = 500
    error_code: str = "INTERNAL_SERVER_ERROR"

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        status_code: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if error_code:
            self.error_code = error_code
        if status_code:
            self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception details to a standard API response dictionary."""
        response = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            response["details"] = self.details
        return response


class BadRequestError(APIException):
    """400 Bad Request"""
    status_code = 400
    error_code = "BAD_REQUEST"


class UnauthorizedError(APIException):
    """401 Unauthorized"""
    status_code = 401
    error_code = "UNAUTHORIZED"


class ForbiddenError(APIException):
    """403 Forbidden"""
    status_code = 403
    error_code = "FORBIDDEN"


class NotFoundError(APIException):
    """404 Not Found"""
    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(APIException):
    """409 Conflict"""
    status_code = 409
    error_code = "CONFLICT"


class QuotaExceededError(APIException):
    """429 Too Many Requests / Quota Limit Exceeded"""
    status_code = 429
    error_code = "QUOTA_EXCEEDED"


class InternalServerError(APIException):
    """500 Internal Server Error"""
    status_code = 500
    error_code = "INTERNAL_SERVER_ERROR"

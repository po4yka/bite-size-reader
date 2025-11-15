"""Custom exceptions and error codes for Mobile API.

Provides standardized error handling with correlation IDs and detailed error messages.
"""

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Standard error codes for API responses."""

    # Client errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_REQUEST = "INVALID_REQUEST"

    # Server errors (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    PROCESSING_ERROR = "PROCESSING_ERROR"


class APIException(Exception):
    """Base exception for all API errors."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class ValidationError(APIException):
    """Raised when request validation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=422,
            details=details,
        )


class AuthenticationError(APIException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            error_code=ErrorCode.AUTHENTICATION_FAILED,
            status_code=401,
        )


class AuthorizationError(APIException):
    """Raised when user is not authorized to access a resource."""

    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            error_code=ErrorCode.AUTHORIZATION_FAILED,
            status_code=403,
        )


class ResourceNotFoundError(APIException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource_type: str, resource_id: int | str):
        super().__init__(
            message=f"{resource_type} with ID {resource_id} not found",
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            details={"resource_type": resource_type, "resource_id": str(resource_id)},
        )


class DuplicateResourceError(APIException):
    """Raised when attempting to create a duplicate resource."""

    def __init__(self, message: str, existing_id: int | str | None = None):
        details = {}
        if existing_id is not None:
            details["existing_id"] = str(existing_id)

        super().__init__(
            message=message,
            error_code=ErrorCode.DUPLICATE_RESOURCE,
            status_code=409,
            details=details,
        )


class RateLimitExceededError(APIException):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after_seconds: int | None = None):
        message = "Rate limit exceeded"
        if retry_after_seconds:
            message += f". Try again in {retry_after_seconds} seconds"

        details = {}
        if retry_after_seconds:
            details["retry_after_seconds"] = retry_after_seconds

        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=429,
            details=details,
        )


class DatabaseError(APIException):
    """Raised when database operations fail."""

    def __init__(self, message: str = "Database error occurred"):
        super().__init__(
            message=message,
            error_code=ErrorCode.DATABASE_ERROR,
            status_code=503,
        )


class ExternalAPIError(APIException):
    """Raised when external API calls fail."""

    def __init__(self, service_name: str, message: str | None = None):
        full_message = f"{service_name} API error"
        if message:
            full_message += f": {message}"

        super().__init__(
            message=full_message,
            error_code=ErrorCode.EXTERNAL_API_ERROR,
            status_code=502,
            details={"service": service_name},
        )


class ProcessingError(APIException):
    """Raised when request processing fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.PROCESSING_ERROR,
            status_code=500,
            details=details,
        )

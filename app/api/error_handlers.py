"""Global exception handlers for the Mobile API.

Provides consistent error responses across all endpoints with correlation ID tracking.
"""

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError as PydanticValidationError

from app.api.exceptions import APIException, ErrorCode, ErrorType
from app.api.models.responses import error_response, make_error
from app.config import load_config

logger = logging.getLogger(__name__)


async def api_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle custom API exceptions."""
    # Type narrowing for FastAPI compatibility
    if not isinstance(exc, APIException):
        raise exc

    correlation_id = getattr(request.state, "correlation_id", None)

    # Log the error
    logger.error(
        f"API error: {exc.error_code.value} - {exc.message}",
        exc_info=False,
        extra={
            "correlation_id": correlation_id,
            "error_code": exc.error_code.value,
            "error_type": exc.error_type.value,
            "status_code": exc.status_code,
            "retryable": exc.retryable,
            "path": request.url.path,
        },
    )

    detail = make_error(
        code=exc.error_code.value,
        message=exc.message,
        error_type=exc.error_type.value,
        retryable=exc.retryable,
        details=exc.details or None,
        retry_after=exc.retry_after,
    )
    detail.correlation_id = correlation_id

    return JSONResponse(
        status_code=exc.status_code, content=error_response(detail, correlation_id=correlation_id)
    )


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle Pydantic validation errors."""
    # Type narrowing for FastAPI compatibility
    if not isinstance(exc, PydanticValidationError):
        raise exc

    correlation_id = getattr(request.state, "correlation_id", None)

    # Format validation errors
    formatted_errors = []
    for error in exc.errors():
        formatted_errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    logger.warning(
        "Request validation failed",
        extra={
            "correlation_id": correlation_id,
            "errors": formatted_errors,
            "path": request.url.path,
        },
    )

    detail = make_error(
        code=ErrorCode.VALIDATION_ERROR.value,
        message="Request validation failed",
        error_type=ErrorType.VALIDATION,
        retryable=False,
        details={"fields": formatted_errors},
    )
    detail.correlation_id = correlation_id

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response(detail, correlation_id=correlation_id),
    )


async def database_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle database-related exceptions."""
    correlation_id = getattr(request.state, "correlation_id", None)

    logger.error(
        f"Database error: {exc}",
        exc_info=True,
        extra={"correlation_id": correlation_id, "path": request.url.path},
    )

    detail = make_error(
        code=ErrorCode.DATABASE_ERROR.value,
        message="Database temporarily unavailable",
        error_type=ErrorType.INTERNAL,
        retryable=True,
    )
    detail.correlation_id = correlation_id

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=error_response(detail, correlation_id=correlation_id),
    )


async def global_exception_handler(request: Request, exc: Exception) -> Response:
    """Catch-all handler for unexpected exceptions."""
    correlation_id = getattr(request.state, "correlation_id", None)

    logger.error(
        f"Unhandled exception: {exc}",
        exc_info=True,
        extra={"correlation_id": correlation_id, "path": request.url.path},
    )

    # Don't leak error details in production
    config = load_config()
    debug_mode = config.runtime.log_level == "DEBUG"

    message = str(exc) if debug_mode else "An internal server error occurred"

    detail = make_error(
        code=ErrorCode.INTERNAL_ERROR.value,
        message=message,
        error_type=ErrorType.INTERNAL,
        retryable=False,
    )
    detail.correlation_id = correlation_id

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(detail, correlation_id=correlation_id),
    )

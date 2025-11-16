"""Global exception handlers for the Mobile API.

Provides consistent error responses across all endpoints with correlation ID tracking.
"""

import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError as PydanticValidationError

from app.api.exceptions import APIException, ErrorCode
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
            "status_code": exc.status_code,
            "path": request.url.path,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.error_code.value,
                "message": exc.message,
                "details": exc.details,
                "correlation_id": correlation_id,
            },
        },
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

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Request validation failed",
                "details": {"fields": formatted_errors},
                "correlation_id": correlation_id,
            },
        },
    )


async def database_exception_handler(request: Request, exc: Exception) -> Response:
    """Handle database-related exceptions."""
    correlation_id = getattr(request.state, "correlation_id", None)

    logger.error(
        f"Database error: {exc}",
        exc_info=True,
        extra={"correlation_id": correlation_id, "path": request.url.path},
    )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.DATABASE_ERROR.value,
                "message": "Database temporarily unavailable",
                "correlation_id": correlation_id,
            },
        },
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

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.INTERNAL_ERROR.value,
                "message": message,
                "correlation_id": correlation_id,
            },
        },
    )

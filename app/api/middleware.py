"""
FastAPI middleware for request processing.
"""

import time
import uuid
from collections.abc import Callable
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

# Simple in-memory rate limiter (use Redis in production)
_rate_limit_store = {}


async def correlation_id_middleware(request: Request, call_next: Callable):
    """
    Add correlation ID to all requests for tracing.

    Checks for X-Correlation-ID header, generates one if missing.
    """
    correlation_id = request.headers.get("X-Correlation-ID")

    if not correlation_id:
        correlation_id = f"api-{uuid.uuid4().hex[:16]}"

    # Store in request state for access in handlers
    request.state.correlation_id = correlation_id

    # Process request
    response = await call_next(request)

    # Add correlation ID to response headers
    response.headers["X-Correlation-ID"] = correlation_id

    return response


async def rate_limit_middleware(request: Request, call_next: Callable):
    """
    Rate limiting middleware.

    TODO: Replace with Redis-based rate limiter for production.
    Current implementation is in-memory and not suitable for multi-process deployments.
    """
    # Get user ID from auth (if authenticated)
    user_id = getattr(request.state, "user_id", None)

    if not user_id:
        # Use IP as fallback for unauthenticated requests
        user_id = request.client.host

    # Rate limit key
    key = f"rate_limit:{user_id}:{int(time.time() / 60)}"  # Per minute

    # Get current count
    current_count = _rate_limit_store.get(key, 0)

    # Rate limits (requests per minute)
    if request.url.path.startswith("/v1/summaries"):
        limit = 200
    elif request.url.path.startswith("/v1/requests"):
        limit = 10
    elif request.url.path.startswith("/v1/search"):
        limit = 50
    else:
        limit = 100

    # Check if exceeded
    if current_count >= limit:
        reset_time = int(time.time() / 60 + 1) * 60

        return JSONResponse(
            status_code=429,
            content={
                "success": False,
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded. Try again in {reset_time - int(time.time())} seconds.",
                    "retry_after": reset_time - int(time.time()),
                },
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
                "Retry-After": str(reset_time - int(time.time())),
            },
        )

    # Increment count
    _rate_limit_store[key] = current_count + 1

    # Process request
    response = await call_next(request)

    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(limit - current_count - 1)
    response.headers["X-RateLimit-Reset"] = str(int(time.time() / 60 + 1) * 60)

    return response


# Clean up old rate limit entries periodically
def cleanup_rate_limit_store():
    """Remove expired rate limit entries."""
    current_minute = int(time.time() / 60)
    expired_keys = [key for key in _rate_limit_store if int(key.split(":")[-1]) < current_minute - 5]

    for key in expired_keys:
        del _rate_limit_store[key]

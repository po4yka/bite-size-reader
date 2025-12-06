"""FastAPI middleware for request processing."""

import time
import uuid
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.context import correlation_id_ctx
from app.api.models.responses import ErrorDetail, error_response
from app.config import AppConfig, load_config
from app.core.logging_utils import get_logger
from app.infrastructure.redis import get_redis, redis_key

logger = get_logger(__name__)

# Cached config for middleware usage
_cfg: AppConfig | None = None
_redis_warning_logged = False


async def correlation_id_middleware(request: Request, call_next: Callable):
    """
    Add correlation ID to all requests for tracing.

    Checks for X-Correlation-ID header, generates one if missing.
    """
    correlation_id = request.headers.get("X-Correlation-ID")

    if not correlation_id:
        correlation_id = f"api-{uuid.uuid4().hex[:16]}"

    # Store in request state and context for access in handlers/helpers
    request.state.correlation_id = correlation_id
    token = correlation_id_ctx.set(correlation_id)

    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        correlation_id_ctx.reset(token)


def _get_cfg() -> AppConfig:
    global _cfg
    if _cfg is None:
        _cfg = load_config(allow_stub_telegram=True)
    return _cfg


def _resolve_limit(path: str, cfg: AppConfig) -> int:
    limits = cfg.api_limits
    if path.startswith("/v1/summaries"):
        return limits.summaries_limit
    if path.startswith("/v1/requests"):
        return limits.requests_limit
    if path.startswith("/v1/search"):
        return limits.search_limit
    return limits.default_limit


async def rate_limit_middleware(request: Request, call_next: Callable):
    """Redis-backed rate limiting middleware with graceful fallback."""
    cfg = _get_cfg()
    correlation_id = getattr(request.state, "correlation_id", None)

    # Identify actor
    user_id = getattr(request.state, "user_id", None) or request.client.host
    bucket_limit = _resolve_limit(request.url.path, cfg)
    window = cfg.api_limits.window_seconds
    now = int(time.time())
    window_start = (now // window) * window

    redis_client = await get_redis(cfg)
    if redis_client is None:
        global _redis_warning_logged
        if not _redis_warning_logged:
            logger.warning(
                "rate_limit_redis_unavailable",
                extra={
                    "required": cfg.redis.required,
                    "correlation_id": correlation_id,
                    "path": request.url.path,
                },
            )
            _redis_warning_logged = True

        if cfg.redis.required:
            detail = ErrorDetail(
                code="RATE_LIMIT_BACKEND_UNAVAILABLE",
                message="Rate limit backend unavailable. Please try again later.",
                correlation_id=correlation_id,
            )
            return JSONResponse(
                status_code=503,
                content=error_response(detail, correlation_id=correlation_id),
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(bucket_limit)
        response.headers["X-RateLimit-Remaining"] = "unknown"
        response.headers["X-RateLimit-Reset"] = str(window_start + window)
        return response

    key = redis_key(cfg.redis.prefix, "rate", str(user_id), str(window_start))

    # Increment counter with TTL in a pipeline
    ttl = max(window + 5, int(window * cfg.api_limits.cooldown_multiplier))
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, ttl)
    count, _ = await pipe.execute()

    if count > bucket_limit:
        retry_after = max(
            (window_start + window) - now, int(window * cfg.api_limits.cooldown_multiplier)
        )
        logger.info(
            "rate_limit_exceeded",
            extra={
                "user_id": user_id,
                "path": request.url.path,
                "limit": bucket_limit,
                "count": count,
                "retry_after": retry_after,
                "correlation_id": correlation_id,
            },
        )
        detail = ErrorDetail(
            code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            details={"retry_after": retry_after},
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=429,
            content=error_response(detail, correlation_id=correlation_id),
            headers={
                "X-RateLimit-Limit": str(bucket_limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(window_start + window),
                "Retry-After": str(retry_after),
            },
        )

    # Process request
    response = await call_next(request)

    remaining = max(bucket_limit - count, 0)
    response.headers["X-RateLimit-Limit"] = str(bucket_limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(window_start + window)

    return response

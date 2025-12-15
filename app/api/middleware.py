"""FastAPI middleware for request processing."""

import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.context import correlation_id_ctx
from app.api.models.responses import ErrorType, error_response, make_error
from app.config import AppConfig, load_config
from app.core.logging_utils import get_logger
from app.infrastructure.redis import get_redis, redis_key

logger = get_logger(__name__)

# Cached config for middleware usage
_cfg: AppConfig | None = None
_redis_warning_logged = False

# In-memory rate limiting fallback when Redis is unavailable
_local_rate_limits: dict[str, list[float]] = defaultdict(list)
_local_rate_lock = threading.Lock()
_local_cleanup_last = 0.0


def _check_local_rate_limit(user_id: str, limit: int, window: int) -> tuple[bool, int]:
    """
    In-memory rate limit check.

    Returns (allowed, remaining) tuple.
    Thread-safe with automatic cleanup of old entries.
    """
    global _local_cleanup_last
    now = time.time()
    window_start = int(now // window) * window
    key = f"{user_id}:{window_start}"

    with _local_rate_lock:
        # Periodic cleanup of stale entries (every 60 seconds)
        if now - _local_cleanup_last > 60:
            stale_keys = [
                k for k in _local_rate_limits if int(k.split(":")[-1]) < window_start - window
            ]
            for k in stale_keys:
                del _local_rate_limits[k]
            _local_cleanup_last = now

        requests = _local_rate_limits[key]
        # Remove old entries outside current window
        requests[:] = [ts for ts in requests if ts >= window_start]

        if len(requests) >= limit:
            return False, 0

        requests.append(now)
        return True, limit - len(requests)


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
            detail = make_error(
                code="RATE_LIMIT_BACKEND_UNAVAILABLE",
                message="Rate limit backend unavailable. Please try again later.",
                error_type=ErrorType.INTERNAL,
                retryable=True,
            )
            detail.correlation_id = correlation_id
            return JSONResponse(
                status_code=503,
                content=error_response(detail, correlation_id=correlation_id),
            )

        # Use in-memory fallback rate limiting instead of bypassing
        allowed, remaining = _check_local_rate_limit(str(user_id), bucket_limit, window)

        if not allowed:
            retry_after = max(
                (window_start + window) - now, int(window * cfg.api_limits.cooldown_multiplier)
            )
            logger.info(
                "rate_limit_exceeded_local",
                extra={
                    "user_id": user_id,
                    "path": request.url.path,
                    "limit": bucket_limit,
                    "retry_after": retry_after,
                    "correlation_id": correlation_id,
                    "backend": "in-memory",
                },
            )
            detail = make_error(
                code="RATE_LIMIT_EXCEEDED",
                message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                error_type=ErrorType.RATE_LIMIT,
                retryable=True,
                details={"retry_after": retry_after},
                retry_after=retry_after,
            )
            detail.correlation_id = correlation_id
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

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(bucket_limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
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
        detail = make_error(
            code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            error_type=ErrorType.RATE_LIMIT,
            retryable=True,
            details={"retry_after": retry_after},
            retry_after=retry_after,
        )
        detail.correlation_id = correlation_id
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

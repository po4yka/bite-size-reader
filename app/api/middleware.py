"""FastAPI middleware for request processing."""

import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.context import correlation_id_ctx
from app.api.exceptions import ErrorType
from app.api.models.responses import error_response, make_error
from app.config import AppConfig, load_config
from app.core.logging_utils import get_logger
from app.infrastructure.redis import get_redis, redis_key

logger = get_logger(__name__)

# Cached config for middleware usage.
# Lazy-initialized on the first request rather than at startup because:
# (1) middleware is loaded before lifespan runs, and (2) config only needs
# to be read once. _get_cfg() below provides thread-safe lazy access.
_cfg: AppConfig | None = None

# One-time warning flag — intentionally global so the "Redis unavailable"
# warning is emitted at most once per process, not once per request.
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


async def webapp_auth_middleware(request: Request, call_next: Callable):
    """Validate Telegram WebApp initData and attach user to request.state.

    When X-Telegram-Init-Data header is present and no Authorization header,
    validates the initData and stores the parsed user in request.state.webapp_user.
    This lets downstream ``get_current_user`` dependency accept WebApp auth
    without modifying every router.
    """
    init_data = request.headers.get("X-Telegram-Init-Data")
    if init_data and "Authorization" not in request.headers:
        try:
            from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

            user = verify_telegram_webapp_init_data(init_data)
            request.state.webapp_user = user
            request.state.user_id = str(user["user_id"])
        except Exception as exc:
            request.state.webapp_auth_error = str(exc)
            logger.debug("webapp_auth_header_parse_failed", extra={"error": str(exc)})
    return await call_next(request)


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


def _resolve_limit(_path: str, cfg: AppConfig) -> int:
    return _resolve_limit_from_bucket(cfg=cfg, bucket=None)


def _resolve_limit_from_bucket(cfg: AppConfig, bucket: str | None) -> int:
    limits = cfg.api_limits
    if bucket == "summaries":
        return limits.summaries_limit
    if bucket == "requests":
        return limits.requests_limit
    if bucket == "search":
        return limits.search_limit
    return limits.default_limit


def _get_user_id_from_auth_header(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        from app.api.routers.auth import decode_token

        payload = decode_token(token, expected_type="access")
    except Exception:
        logger.warning("jwt_decode_failed_for_rate_limit")
        return None
    user_id = payload.get("user_id")
    if isinstance(user_id, int):
        return str(user_id)
    if isinstance(user_id, str) and user_id.isdigit():
        return user_id
    return None


def _resolve_rate_limit_actor(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None) or _get_user_id_from_auth_header(request)
    if not user_id:
        webapp_user = getattr(request.state, "webapp_user", None)
        if isinstance(webapp_user, dict):
            webapp_user_id = webapp_user.get("user_id")
            if isinstance(webapp_user_id, int):
                user_id = str(webapp_user_id)
            elif isinstance(webapp_user_id, str) and webapp_user_id.isdigit():
                user_id = webapp_user_id
    if user_id:
        return str(user_id)
    return request.client.host if request.client and request.client.host else "unknown"


def _build_rate_limit_response(
    *,
    correlation_id: str | None,
    code: str,
    message: str,
    error_type: ErrorType,
    status_code: int,
    retry_after: int | None = None,
    limit: int | None = None,
    remaining: int | None = None,
    reset: int | None = None,
) -> JSONResponse:
    detail_kwargs: dict[str, Any] = {
        "code": code,
        "message": message,
        "error_type": error_type,
        "retryable": True,
    }
    if retry_after is not None:
        detail_kwargs["details"] = {"retry_after": retry_after}
        detail_kwargs["retry_after"] = retry_after
    detail = make_error(**detail_kwargs)
    detail.correlation_id = correlation_id

    headers: dict[str, str] = {}
    if limit is not None:
        headers["X-RateLimit-Limit"] = str(limit)
    if remaining is not None:
        headers["X-RateLimit-Remaining"] = str(remaining)
    if reset is not None:
        headers["X-RateLimit-Reset"] = str(reset)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=status_code,
        content=error_response(detail, correlation_id=correlation_id),
        headers=headers or None,
    )


def _attach_rate_limit_headers(
    *,
    response: Any,
    limit: int,
    remaining: int,
    window_start: int,
    window: int,
) -> Any:
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
    response.headers["X-RateLimit-Reset"] = str(window_start + window)
    return response


def _compute_retry_after(now: int, window_start: int, window: int, cfg: AppConfig) -> int:
    return max((window_start + window) - now, int(window * cfg.api_limits.cooldown_multiplier))


def _log_redis_unavailable_once(cfg: AppConfig, correlation_id: str | None, path: str) -> None:
    global _redis_warning_logged
    if _redis_warning_logged:
        return
    logger.warning(
        "rate_limit_redis_unavailable",
        extra={
            "required": cfg.redis.required,
            "correlation_id": correlation_id,
            "path": path,
        },
    )
    _redis_warning_logged = True


async def _handle_local_rate_limit(
    *,
    request: Request,
    call_next: Callable,
    cfg: AppConfig,
    correlation_id: str | None,
    user_id: str,
    bucket_limit: int,
    window: int,
    window_start: int,
    now: int,
) -> JSONResponse | Any:
    allowed, remaining = _check_local_rate_limit(user_id, bucket_limit, window)
    if not allowed:
        retry_after = _compute_retry_after(now, window_start, window, cfg)
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
        return _build_rate_limit_response(
            correlation_id=correlation_id,
            code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            error_type=ErrorType.RATE_LIMIT,
            status_code=429,
            retry_after=retry_after,
            limit=bucket_limit,
            remaining=0,
            reset=window_start + window,
        )

    response = await call_next(request)
    return _attach_rate_limit_headers(
        response=response,
        limit=bucket_limit,
        remaining=remaining,
        window_start=window_start,
        window=window,
    )


async def _handle_redis_rate_limit(
    *,
    request: Request,
    call_next: Callable,
    cfg: AppConfig,
    correlation_id: str | None,
    redis_client: Any,
    user_id: str,
    bucket_limit: int,
    window: int,
    window_start: int,
    now: int,
) -> JSONResponse | Any:
    key = redis_key(cfg.redis.prefix, "rate", user_id, str(window_start))
    ttl = max(window + 5, int(window * cfg.api_limits.cooldown_multiplier))
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, ttl)
    count, _ = await pipe.execute()

    if count > bucket_limit:
        retry_after = _compute_retry_after(now, window_start, window, cfg)
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
        return _build_rate_limit_response(
            correlation_id=correlation_id,
            code="RATE_LIMIT_EXCEEDED",
            message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            error_type=ErrorType.RATE_LIMIT,
            status_code=429,
            retry_after=retry_after,
            limit=bucket_limit,
            remaining=0,
            reset=window_start + window,
        )

    response = await call_next(request)
    return _attach_rate_limit_headers(
        response=response,
        limit=bucket_limit,
        remaining=max(bucket_limit - count, 0),
        window_start=window_start,
        window=window,
    )


async def rate_limit_middleware(request: Request, call_next: Callable):
    """Redis-backed rate limiting middleware with graceful fallback."""
    cfg = _get_cfg()
    correlation_id = getattr(request.state, "correlation_id", None)

    user_id = _resolve_rate_limit_actor(request)

    # Simple path-based rate limit bucket resolution
    path = request.url.path
    bucket: str | None = None
    if "/summaries" in path:
        bucket = "summaries"
    elif "/search" in path:
        bucket = "search"
    elif "/requests" in path:
        bucket = "requests"

    request.state.interface_route_key = path
    request.state.interface_route_requires_auth = True

    bucket_limit = _resolve_limit_from_bucket(cfg=cfg, bucket=bucket)
    window = cfg.api_limits.window_seconds
    now = int(time.time())
    window_start = (now // window) * window

    redis_client = await get_redis(cfg)
    if redis_client is None:
        _log_redis_unavailable_once(cfg, correlation_id, request.url.path)

        if cfg.redis.required:
            return _build_rate_limit_response(
                correlation_id=correlation_id,
                code="RATE_LIMIT_BACKEND_UNAVAILABLE",
                message="Rate limit backend unavailable. Please try again later.",
                error_type=ErrorType.INTERNAL,
                status_code=503,
            )
        return await _handle_local_rate_limit(
            request=request,
            call_next=call_next,
            cfg=cfg,
            correlation_id=correlation_id,
            user_id=user_id,
            bucket_limit=bucket_limit,
            window=window,
            window_start=window_start,
            now=now,
        )

    return await _handle_redis_rate_limit(
        request=request,
        call_next=call_next,
        cfg=cfg,
        correlation_id=correlation_id,
        redis_client=redis_client,
        user_id=user_id,
        bucket_limit=bucket_limit,
        window=window,
        window_start=window_start,
        now=now,
    )

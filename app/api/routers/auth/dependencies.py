"""
FastAPI authentication dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

try:
    from fastapi import Depends, Request  # noqa: TC002 - used at runtime by FastAPI DI
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except Exception:  # pragma: no cover - fallback for environments without compatible FastAPI
    logging.getLogger(__name__).debug("fastapi_security_import_failed", exc_info=True)

    class HTTPAuthorizationCredentials:  # type: ignore[no-redef]
        ...

    class HTTPBearer:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    def Depends(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc, unused-ignore]  # noqa: N802
        return None


from app.api.dependencies.database import get_auth_repository as get_db_auth_repository
from app.api.exceptions import AuthenticationError, AuthorizationError
from app.api.routers.auth.tokens import decode_token, validate_client_id
from app.config import Config

if TYPE_CHECKING:
    from app.infrastructure.persistence.sqlite.repositories.auth_repository import (
        SqliteAuthRepositoryAdapter,
    )

logger = logging.getLogger(__name__)

# HTTPBearer security scheme for JWT authentication
# auto_error=False so missing Bearer token doesn't 403 before we check WebApp auth
security = HTTPBearer(auto_error=False)

# Cached instances for dependency injection
_auth_token_cache: Any = None
_redis_cache: Any = None


def _get_auth_token_cache() -> Any:
    """Get or create the auth token cache singleton."""
    global _auth_token_cache, _redis_cache

    if _auth_token_cache is not None:
        return _auth_token_cache

    try:
        from app.config import load_config
        from app.infrastructure.cache.auth_token_cache import AuthTokenCache
        from app.infrastructure.cache.redis_cache import RedisCache

        config = load_config(allow_stub_telegram=True)
        if not config.redis.enabled:
            return None

        if _redis_cache is None:
            _redis_cache = RedisCache(config)

        _auth_token_cache = AuthTokenCache(_redis_cache, config)
        return _auth_token_cache
    except Exception as exc:
        logger.warning(
            "auth_token_cache_init_failed",
            extra={"error": str(exc)},
        )
        return None


def get_auth_repository() -> SqliteAuthRepositoryAdapter:
    """Dependency to get auth repository with optional Redis caching.

    Returns:
        SqliteAuthRepositoryAdapter with token cache if Redis is available.
    """
    token_cache = _get_auth_token_cache()
    return get_db_auth_repository(token_cache=token_cache)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """
    Dependency to get current authenticated user.

    Supports two auth methods:
    1. JWT Bearer token (mobile app / API clients)
    2. Telegram WebApp initData (Mini App -- set by webapp_auth_middleware)

    When both are present, JWT takes precedence.

    Raises:
        TokenExpiredError: Access token has expired (401)
        TokenInvalidError: Token is malformed (401)
        TokenWrongTypeError: Not an access token (401)
        AuthorizationError: User not in whitelist (403)
        AuthenticationError: No valid auth method found (401)
    """
    # Check WebApp auth first (set by webapp_auth_middleware)
    webapp_user = getattr(request.state, "webapp_user", None)

    # If we have JWT credentials, use JWT auth (takes precedence)
    if credentials is not None:
        from app.api.exceptions import TokenInvalidError

        token = credentials.credentials
        payload = decode_token(token, expected_type="access")

        user_id = payload.get("user_id")
        if not user_id:
            raise TokenInvalidError("Missing user_id in token payload")

        # Verify user is still in whitelist when configured.
        # JWT auth is intentionally optional-whitelist: when ALLOWED_USER_IDS is unset,
        # any JWT-authenticated user is permitted (supports multi-user deployments).
        # WebApp auth (webapp_auth.py) is fail-closed: raises if whitelist is unset.
        allowed_ids = Config.get_allowed_user_ids()
        if allowed_ids and user_id not in allowed_ids:
            raise AuthorizationError("User not authorized")

        # Validate client_id from token
        client_id = payload.get("client_id")
        validate_client_id(client_id)

        return {
            "user_id": user_id,
            "username": payload.get("username"),
            "client_id": client_id,
        }

    # Fall back to WebApp auth
    if webapp_user is not None:
        return {
            "user_id": webapp_user["user_id"],
            "username": webapp_user.get("username"),
            "client_id": "webapp",
        }

    # No valid auth method found
    raise AuthenticationError("Authentication required")


def get_webapp_user(request: Request) -> dict:
    """Dependency to get user from Telegram WebApp initData.

    Validates the X-Telegram-Init-Data header using HMAC-SHA256.
    """
    from app.api.routers.auth.webapp_auth import verify_telegram_webapp_init_data

    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        raise AuthenticationError("Missing X-Telegram-Init-Data header")
    return verify_telegram_webapp_init_data(init_data)

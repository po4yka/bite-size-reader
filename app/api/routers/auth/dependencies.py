"""
FastAPI authentication dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

try:
    from fastapi import Depends
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


from app.api.exceptions import AuthorizationError
from app.api.routers.auth.tokens import decode_token, validate_client_id
from app.config import Config

if TYPE_CHECKING:
    from app.infrastructure.persistence.sqlite.repositories.auth_repository import (
        SqliteAuthRepositoryAdapter,
    )

logger = logging.getLogger(__name__)

# HTTPBearer security scheme for JWT authentication
security = HTTPBearer()

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
        from app.infrastructure.cache import AuthTokenCache, RedisCache

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
    from app.db.models import database_proxy
    from app.infrastructure.persistence.sqlite.repositories.auth_repository import (
        SqliteAuthRepositoryAdapter,
    )

    token_cache = _get_auth_token_cache()
    return SqliteAuthRepositoryAdapter(database_proxy, token_cache=token_cache)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get current authenticated user.

    Validates JWT token and returns user data.

    Raises:
        TokenExpiredError: Access token has expired (401)
        TokenInvalidError: Token is malformed (401)
        TokenWrongTypeError: Not an access token (401)
        AuthorizationError: User not in whitelist (403)
    """
    from app.api.exceptions import TokenInvalidError

    token = credentials.credentials
    payload = decode_token(token, expected_type="access")

    user_id = payload.get("user_id")
    if not user_id:
        raise TokenInvalidError("Missing user_id in token payload")

    # Verify user is still in whitelist when configured
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

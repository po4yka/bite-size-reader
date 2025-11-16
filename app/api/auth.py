"""
Compatibility layer for authentication dependencies.

Historically the API routers imported authentication helpers from ``app.api.auth``.
The actual implementations now live in ``app.api.routers.auth`` so this module
re-exports the runtime helpers and keeps the public import path stable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Depends

if TYPE_CHECKING:
    from fastapi.security import HTTPAuthorizationCredentials
else:
    HTTPAuthorizationCredentials = Any

from app.api.routers import auth as auth_router

# Re-export frequently used helpers
validate_client_id = auth_router.validate_client_id
decode_token = auth_router.decode_token
verify_telegram_auth = auth_router.verify_telegram_auth
create_token = auth_router.create_token
create_access_token = auth_router.create_access_token
create_refresh_token = auth_router.create_refresh_token

# Share the same HTTPBearer dependency to avoid duplicate middleware wiring
security = auth_router.security


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Delegate to the router implementation for dependency injection."""
    return await auth_router.get_current_user(credentials)


__all__ = [
    "create_access_token",
    "create_refresh_token",
    "create_token",
    "decode_token",
    "get_current_user",
    "validate_client_id",
    "verify_telegram_auth",
]

"""
Token refresh, logout, and session listing endpoints.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from app.api.exceptions import ResourceNotFoundError
from app.api.models.auth import RefreshTokenRequest, SessionInfo
from app.api.models.responses import (
    AuthTokensResponse,
    SessionListResponse,
    TokenPair,
    success_response,
)
from app.api.routers.auth._fastapi import APIRouter, Depends
from app.api.routers.auth.dependencies import get_current_user
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    decode_token,
    validate_client_id,
)
from app.core.logging_utils import get_logger, log_exception
from app.core.time_utils import UTC
from app.db.models import database_proxy
from app.infrastructure.persistence.sqlite.repositories.auth_repository import (
    SqliteAuthRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)

logger = get_logger(__name__)
router = APIRouter()


def _format_dt_z(dt_value: Any) -> str:
    if dt_value is None:
        return ""
    if hasattr(dt_value, "isoformat"):
        return dt_value.isoformat() + "Z"
    value = str(dt_value)
    return value if value.endswith("Z") else value + "Z"


@router.post("/refresh")
async def refresh_access_token(refresh_data: RefreshTokenRequest):
    """Refresh an expired access token using a refresh token."""
    from app.api.exceptions import TokenInvalidError, TokenRevokedError

    payload = decode_token(refresh_data.refresh_token, expected_type="refresh")
    user_id = payload.get("user_id")
    if not user_id:
        raise TokenInvalidError("Missing user_id in token payload")

    client_id = payload.get("client_id")
    validate_client_id(client_id)

    token_hash = hashlib.sha256(refresh_data.refresh_token.encode()).hexdigest()
    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    refresh_token_record = await auth_repo.async_get_refresh_token_by_hash(token_hash)
    if not refresh_token_record:
        raise TokenInvalidError("Refresh token is not recognized")
    if refresh_token_record.get("is_revoked"):
        raise TokenRevokedError()

    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user = await user_repo.async_get_user_by_telegram_id(user_id)
    if not user:
        raise ResourceNotFoundError("User", user_id)

    await auth_repo.async_update_refresh_token_last_used(refresh_token_record["id"])
    access_token = create_access_token(
        user.get("telegram_user_id", user_id),
        user.get("username"),
        client_id,
    )

    logger.info("token_refreshed", extra={"user_id": user_id, "client_id": client_id})

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=None,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )
    return success_response(AuthTokensResponse(tokens=tokens))


@router.post("/logout")
async def logout(request: RefreshTokenRequest, _: dict = Depends(get_current_user)):
    """Logout by revoking the specific refresh token."""
    token = request.refresh_token
    try:
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
        revoked = await auth_repo.async_revoke_refresh_token(token_hash)
        if revoked:
            logger.info("refresh_token_revoked", extra={"token_hash": token_hash[:8] + "..."})
    except Exception as e:
        log_exception(logger, "logout_failed", e, level="warning")

    return success_response({"message": "Logged out successfully"})


@router.get("/sessions")
async def list_sessions(current_user: dict = Depends(get_current_user)) -> dict:
    """List active sessions for the current user."""
    user_id = current_user["user_id"]
    now = datetime.now(UTC)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    sessions = await auth_repo.async_list_active_sessions(user_id, now)

    formatted_sessions = []
    for s in sessions:
        formatted_sessions.append(
            SessionInfo(
                id=s.get("id", 0),
                client_id=s.get("client_id"),
                device_info=s.get("device_info"),
                ip_address=s.get("ip_address"),
                last_used_at=_format_dt_z(s.get("last_used_at")),
                created_at=_format_dt_z(s.get("created_at")),
            )
        )

    return success_response(SessionListResponse(sessions=formatted_sessions))

"""
Token refresh, logout, and session listing endpoints.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from starlette.requests import Request  # noqa: TC002 - needed at runtime for FastAPI DI
from starlette.responses import Response  # noqa: TC002 - needed at runtime for FastAPI DI

from app.api.dependencies.database import get_user_repository
from app.api.exceptions import AuthorizationError, ResourceNotFoundError
from app.api.models.auth import RefreshTokenRequest, SessionInfo
from app.api.models.responses import (
    AuthTokensResponse,
    SessionListResponse,
    TokenPair,
    success_response,
)
from app.api.routers.auth._fastapi import APIRouter, Depends
from app.api.routers.auth.cookies import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    set_refresh_cookie,
)
from app.api.routers.auth.dependencies import get_auth_repository, get_current_user
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_client_id,
)
from app.core.logging_utils import get_logger, log_exception
from app.core.time_utils import UTC

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
async def refresh_access_token(
    request: Request,
    response: Response,
    refresh_data: RefreshTokenRequest,
    auth_repo: Any = Depends(get_auth_repository),
):
    """Refresh an expired access token using a refresh token."""
    from app.api.exceptions import TokenInvalidError, TokenRevokedError

    # Resolve refresh token: prefer body, fall back to httpOnly cookie
    raw_token = refresh_data.refresh_token or request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise TokenInvalidError("No refresh token provided")

    payload = decode_token(raw_token, expected_type="refresh")
    user_id = payload.get("user_id")
    if not user_id:
        raise TokenInvalidError("Missing user_id in token payload")

    client_id = payload.get("client_id")
    validate_client_id(client_id)

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    refresh_token_record = await auth_repo.async_get_refresh_token_by_hash(token_hash)
    if not refresh_token_record:
        raise TokenInvalidError("Refresh token is not recognized")

    # Reuse detection: a revoked token being replayed indicates potential theft.
    # Revoke ALL tokens for the user as a precaution.
    if refresh_token_record.get("is_revoked"):
        revoked_count = await auth_repo.async_revoke_all_user_tokens(user_id)
        logger.warning(
            "refresh_token_reuse_detected",
            extra={"user_id": user_id, "revoked_count": revoked_count},
        )
        clear_refresh_cookie(response)
        raise TokenRevokedError()

    user_repo = get_user_repository()
    user = await user_repo.async_get_user_by_telegram_id(user_id)
    if not user:
        raise ResourceNotFoundError("User", user_id)

    # Rotate: revoke old token, issue new one
    await auth_repo.async_revoke_refresh_token(token_hash)
    new_refresh_token, session_id = await create_refresh_token(
        user_id=user_id,
        client_id=client_id,
        auth_repo=auth_repo,
    )

    access_token = create_access_token(
        user.get("telegram_user_id", user_id),
        user.get("username"),
        client_id,
    )

    logger.info("session_refreshed", extra={"user_id": user_id, "client_id": client_id})

    # Set the new refresh token as httpOnly cookie for web clients
    set_refresh_cookie(response, new_refresh_token)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )
    return success_response(AuthTokensResponse(tokens=tokens, session_id=session_id))


@router.post("/logout")
async def logout(
    http_request: Request,
    response: Response,
    request: RefreshTokenRequest,
    current_user: dict = Depends(get_current_user),
    auth_repo: Any = Depends(get_auth_repository),
):
    """Logout by revoking the specific refresh token."""
    token = request.refresh_token or http_request.cookies.get(REFRESH_COOKIE_NAME)
    if token:
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            record = await auth_repo.async_get_refresh_token_by_hash(token_hash)
            if record is None:
                raise ResourceNotFoundError("RefreshToken", token_hash[:8])
            # model_to_dict() returns "user" for ForeignKeyField; cache may return "user_id"
            record_user_id = record.get("user_id") or record.get("user")
            if str(record_user_id) != str(current_user.get("user_id")):
                raise AuthorizationError("Token does not belong to the authenticated user")
            revoked = await auth_repo.async_revoke_refresh_token(token_hash)
            if revoked:
                logger.info("refresh_session_revoked")
        except (ResourceNotFoundError, AuthorizationError):
            raise
        except Exception as e:
            log_exception(logger, "logout_failed", e, level="warning")

    clear_refresh_cookie(response)
    return success_response({"message": "Logged out successfully"})


@router.get("/sessions")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
    auth_repo: Any = Depends(get_auth_repository),
) -> dict:
    """List active sessions for the current user."""
    user_id = current_user["user_id"]
    now = datetime.now(UTC)

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


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: int,
    current_user: dict = Depends(get_current_user),
    auth_repo: Any = Depends(get_auth_repository),
) -> dict:
    """Revoke a specific session by ID. Cannot revoke the current session via this endpoint."""
    user_id = current_user["user_id"]
    revoked = await auth_repo.async_revoke_session_by_id(session_id, user_id)
    if not revoked:
        raise ResourceNotFoundError("Session", session_id)
    logger.info("session_revoked", extra={"user_id": user_id, "session_id": session_id})
    return success_response({"id": session_id, "revoked": True})

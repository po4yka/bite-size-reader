"""
JWT token creation and validation.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import jwt

from app.api.exceptions import (
    AuthorizationError,
    ValidationError,
)
from app.config import Config
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC

if TYPE_CHECKING:
    from app.infrastructure.persistence.sqlite.repositories.auth_repository import (
        SqliteAuthRepositoryAdapter,
    )

logger = get_logger(__name__)


def _load_secret_key() -> str:
    """Load and validate the JWT secret key."""
    try:
        raw_secret = Config.get("JWT_SECRET_KEY", "")
    except ValueError as err:
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable must be configured. "
            "Generate one with: openssl rand -hex 32"
        ) from err

    secret = (raw_secret or "").strip()

    if not secret or secret == "your-secret-key-change-in-production":
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable must be set to a secure random value. "
            "Generate one with: openssl rand -hex 32"
        )

    if len(secret) < 32:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be at least 32 characters long. Current length: {len(secret)}"
        )
    return secret


# JWT configuration
SECRET_KEY = _load_secret_key()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

logger.info("JWT authentication initialized with secure secret")


def create_token(
    user_id: int, token_type: str, username: str | None = None, client_id: str | None = None
) -> str:
    """
    Create JWT token (access or refresh).

    Args:
        user_id: User ID to encode in token
        token_type: "access" or "refresh"
        username: Optional username to include
        client_id: Optional client application ID to include

    Returns:
        Encoded JWT token
    """
    if token_type == "access":
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        payload = {
            "user_id": user_id,
            "username": username,
            "client_id": client_id,
            "exp": expire,
            "type": "access",
            "iat": datetime.now(UTC),
        }
    elif token_type == "refresh":
        expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "user_id": user_id,
            "client_id": client_id,
            "exp": expire,
            "type": "refresh",
            "iat": datetime.now(UTC),
        }
    else:
        raise ValueError(f"Invalid token type: {token_type}")

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(
    user_id: int, username: str | None = None, client_id: str | None = None
) -> str:
    """Create JWT access token."""
    return create_token(user_id, "access", username, client_id)


async def create_refresh_token(
    user_id: int,
    client_id: str | None = None,
    device_info: str | None = None,
    ip_address: str | None = None,
    auth_repo: SqliteAuthRepositoryAdapter | None = None,
) -> tuple[str, int]:
    """Create and persist JWT refresh token.

    Args:
        user_id: Telegram user ID.
        client_id: Client application identifier.
        device_info: Device information string.
        ip_address: Client IP address.
        auth_repo: Optional auth repository with cache. If None, creates one.

    Returns:
        Tuple of (token_string, session_id) where session_id is the refresh token record ID.
    """
    token = create_token(user_id, "refresh", client_id=client_id)

    # Persist token hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    if auth_repo is None:
        from app.api.routers.auth.dependencies import get_auth_repository

        auth_repo = get_auth_repository()

    session_id = await auth_repo.async_create_refresh_token(
        user_id=user_id,
        token_hash=token_hash,
        client_id=client_id,
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
    )

    return token, session_id


def decode_token(token: str, expected_type: str | None = None) -> dict:
    """Decode and validate JWT token.

    Args:
        token: The JWT token string
        expected_type: If provided, validates token type matches (access/refresh)

    Raises:
        TokenExpiredError: Token has expired (401)
        TokenInvalidError: Token is malformed or signature invalid (401)
        TokenWrongTypeError: Token type doesn't match expected (401)
    """
    from app.api.exceptions import TokenExpiredError, TokenInvalidError, TokenWrongTypeError

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        token_type = expected_type or "access"
        raise TokenExpiredError(token_type) from None
    except jwt.InvalidTokenError as err:
        raise TokenInvalidError(str(err)) from err

    if expected_type and payload.get("type") != expected_type:
        raise TokenWrongTypeError(expected=expected_type, received=payload.get("type", "unknown"))

    return payload


def validate_client_id(client_id: str | None) -> bool:
    """
    Validate client_id against allowlist.

    Args:
        client_id: Client application ID to validate

    Returns:
        True if valid

    Raises:
        ValidationError: If client_id is missing or invalid format
        AuthorizationError: If client_id is not in allowlist
    """
    if not client_id:
        raise ValidationError(
            "Client ID is required. Please update your app to the latest version.",
            details={"field": "client_id"},
        )

    # Validate format
    if not all(c.isalnum() or c in "-_." for c in client_id):
        logger.warning(
            f"Invalid client ID format: {client_id}",
            extra={"client_id": client_id},
        )
        raise ValidationError("Invalid client ID format.", details={"field": "client_id"})

    if len(client_id) > 100:
        logger.warning(
            f"Client ID too long: {client_id}",
            extra={"client_id": client_id, "length": len(client_id)},
        )
        raise ValidationError("Invalid client ID format.", details={"field": "client_id"})

    # Check against allowlist
    allowed_client_ids = Config.get_allowed_client_ids()

    # If allowlist is empty, allow all clients (backward compatible)
    if not allowed_client_ids:
        return True

    # Otherwise, client must be in allowlist
    if client_id not in allowed_client_ids:
        logger.warning(
            f"Client ID not in allowlist: {client_id}",
            extra={"client_id": client_id, "allowed_ids": list(allowed_client_ids)},
        )
        raise AuthorizationError("Client application not authorized. Please contact administrator.")

    return True

"""
Authentication endpoints and utilities.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

try:
    from fastapi import APIRouter, Depends, HTTPException
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
except Exception:  # pragma: no cover - fallback for environments without compatible FastAPI

    class HTTPException(Exception):  # type: ignore[no-redef]
        """Lightweight stand-in for FastAPI's HTTPException."""

        def __init__(self, status_code: int, detail: str | None = None):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail or "")

    class HTTPAuthorizationCredentials:  # type: ignore[no-redef]
        ...

    class HTTPBearer:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            pass

    APIRouter: Any = type("APIRouter", (), {})  # type: ignore

    def Depends(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc, unused-ignore]  # noqa: N802
        return None


from pydantic import BaseModel, ConfigDict, Field

from app.api.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    FeatureDisabledError,
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from app.api.models.responses import (
    AuthTokensResponse,
    TokenPair,
    UserInfo,
    success_response,
)
from app.config import AppConfig, Config, load_config
from app.core.logging_utils import get_logger
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
security = HTTPBearer()
_cfg: AppConfig | None = None


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


# OAuth provider public key URLs
APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
GOOGLE_KEYS_URL = "https://www.googleapis.com/oauth2/v3/certs"
APPLE_ISSUER = "https://appleid.apple.com"

# Cache for JWKS clients (thread-safe, handles key rotation automatically)
_apple_jwks_client: PyJWKClient | None = None
_google_jwks_client: PyJWKClient | None = None


def _get_apple_jwks_client() -> PyJWKClient:
    """Get or create Apple JWKS client."""
    global _apple_jwks_client
    if _apple_jwks_client is None:
        _apple_jwks_client = PyJWKClient(APPLE_KEYS_URL, cache_keys=True, lifespan=3600)
    return _apple_jwks_client


def _get_google_jwks_client() -> PyJWKClient:
    """Get or create Google JWKS client."""
    global _google_jwks_client
    if _google_jwks_client is None:
        _google_jwks_client = PyJWKClient(GOOGLE_KEYS_URL, cache_keys=True, lifespan=3600)
    return _google_jwks_client


def verify_apple_id_token(id_token: str, client_id: str) -> dict[str, Any]:
    """Verify an Apple Sign-In ID token and return the claims.

    Args:
        id_token: The JWT token from Apple Sign-In
        client_id: The expected audience (your app's bundle ID)

    Returns:
        Decoded token claims including 'sub' (user identifier)

    Raises:
        AuthenticationError: If token verification fails
    """
    try:
        jwks_client = _get_apple_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=APPLE_ISSUER,
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )

        logger.info(
            "Apple token verified successfully",
            extra={"sub": claims.get("sub"), "email": claims.get("email")},
        )
        return claims

    except PyJWTError as e:
        logger.warning(
            "Apple token verification failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise AuthenticationError(f"Invalid Apple ID token: {e}") from e
    except Exception as e:
        logger.error(
            "Apple token verification error",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        raise AuthenticationError("Failed to verify Apple ID token") from e


def verify_google_id_token(id_token: str, client_id: str) -> dict[str, Any]:
    """Verify a Google Sign-In ID token and return the claims.

    Args:
        id_token: The JWT token from Google Sign-In
        client_id: The expected audience (your OAuth client ID)

    Returns:
        Decoded token claims including 'sub' (user identifier)

    Raises:
        AuthenticationError: If token verification fails
    """
    try:
        jwks_client = _get_google_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=["https://accounts.google.com", "accounts.google.com"],
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )

        # Additional Google-specific validation
        if not claims.get("email_verified", False):
            logger.warning(
                "Google token has unverified email",
                extra={"sub": claims.get("sub"), "email": claims.get("email")},
            )
            # Allow login but log warning - email verification is recommended

        logger.info(
            "Google token verified successfully",
            extra={
                "sub": claims.get("sub"),
                "email": claims.get("email"),
                "email_verified": claims.get("email_verified"),
            },
        )
        return claims

    except PyJWTError as e:
        logger.warning(
            "Google token verification failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        raise AuthenticationError(f"Invalid Google ID token: {e}") from e
    except Exception as e:
        logger.error(
            "Google token verification error",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        raise AuthenticationError("Failed to verify Google ID token") from e


def _derive_user_id_from_sub(provider: str, sub: str) -> int:
    """Derive a consistent numeric user ID from an OAuth provider's 'sub' claim.

    Args:
        provider: Provider name (e.g., 'apple', 'google')
        sub: The 'sub' (subject) claim from the ID token

    Returns:
        A consistent numeric user ID derived from the sub claim
    """
    # Combine provider and sub to ensure uniqueness across providers
    combined = f"{provider}:{sub}"
    # Use SHA256 to get a consistent hash, then take last 15 digits to stay within int range
    hash_hex = hashlib.sha256(combined.encode()).hexdigest()
    # Use modulo to keep within a reasonable range (positive int)
    return int(hash_hex, 16) % 10**15


def _get_cfg() -> AppConfig:
    """Load and cache application configuration."""
    global _cfg
    if _cfg is None:
        _cfg = load_config(allow_stub_telegram=True)
    return _cfg


def _get_auth_config():
    cfg = _get_cfg()
    return cfg.auth


def _get_secret_pepper() -> str:
    """Resolve pepper used to hash secrets (prefers explicit pepper, falls back to JWT secret)."""
    cfg = _get_cfg()
    if cfg.auth.secret_pepper:
        return cfg.auth.secret_pepper
    if cfg.runtime.jwt_secret_key:
        return cfg.runtime.jwt_secret_key
    return SECRET_KEY


def _coerce_naive(dt_value: datetime | None) -> datetime | None:
    if dt_value is None:
        return None
    if dt_value.tzinfo:
        return dt_value.replace(tzinfo=None)
    return dt_value


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TelegramLoginRequest(BaseModel):
    """Request body for Telegram login."""

    model_config = ConfigDict(populate_by_name=True)

    telegram_user_id: int = Field(..., alias="id")
    auth_hash: str = Field(..., alias="hash")
    auth_date: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    photo_url: str | None = None
    client_id: str = Field(
        ...,
        description="Client application ID (e.g., 'android-app-v1.0', 'ios-app-v2.0')",
        min_length=1,
        max_length=100,
    )


class AppleLoginRequest(BaseModel):
    """Request body for Apple login."""

    id_token: str
    client_id: str
    authorization_code: str | None = None
    given_name: str | None = None
    family_name: str | None = None


class GoogleLoginRequest(BaseModel):
    """Request body for Google login."""

    id_token: str
    client_id: str


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class SecretLoginRequest(BaseModel):
    """Request body for secret-key login."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    client_id: str = Field(..., min_length=1, max_length=100)
    secret: str = Field(..., min_length=8)
    username: str | None = None


class SecretKeyCreateRequest(BaseModel):
    """Request body to create or register a client secret."""

    user_id: int
    client_id: str = Field(..., min_length=1, max_length=100)
    label: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None
    secret: str | None = Field(
        default=None,
        description="Optional client-generated secret; if omitted, server will generate",
    )
    username: str | None = None


class SecretKeyRotateRequest(BaseModel):
    """Request body to rotate an existing client secret."""

    label: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None
    secret: str | None = Field(
        default=None,
        description="Optional client-generated secret; if omitted, server will generate",
    )


class SecretKeyRevokeRequest(BaseModel):
    """Request body to revoke an existing client secret."""

    reason: str | None = Field(default=None, max_length=200)


class ClientSecretInfo(BaseModel):
    """Safe representation of a stored client secret (no hash included)."""

    id: int
    user_id: int
    client_id: str
    status: str
    label: str | None = None
    description: str | None = None
    expires_at: str | None = None
    last_used_at: str | None = None
    failed_attempts: int
    locked_until: str | None = None
    created_at: str
    updated_at: str


class SecretKeyCreateResponse(BaseModel):
    """Payload returned when creating or rotating a secret key."""

    secret: str
    key: ClientSecretInfo


class SecretKeyActionResponse(BaseModel):
    """Payload for list/revoke actions."""

    key: ClientSecretInfo


class SecretKeyListResponse(BaseModel):
    """Payload for listing stored secrets."""

    keys: list[ClientSecretInfo]


class TelegramLinkStatus(BaseModel):
    """Link status payload."""

    linked: bool
    telegram_user_id: int | None = None
    username: str | None = None
    photo_url: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linked_at: str | None = None
    link_nonce_expires_at: str | None = None
    link_nonce: str | None = None


class TelegramLinkBeginResponse(BaseModel):
    """Begin link payload with nonce."""

    nonce: str
    expires_at: str


def verify_telegram_auth(
    user_id: int,
    auth_hash: str,
    auth_date: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    photo_url: str | None = None,
) -> bool:
    """
    Verify Telegram authentication hash.

    Implements the verification algorithm from:
    https://core.telegram.org/widgets/login#checking-authorization

    Args:
        user_id: Telegram user ID
        auth_hash: Authentication hash from Telegram
        auth_date: Timestamp when auth was created
        username: Optional Telegram username
        first_name: Optional first name
        last_name: Optional last name
        photo_url: Optional profile photo URL

    Returns:
        True if authentication is valid

    Raises:
        HTTPException: If authentication fails
    """
    # Check timestamp freshness (15 minute window)
    current_time = int(time.time())
    age_seconds = current_time - auth_date

    if age_seconds > 900:  # 15 minutes
        logger.warning(
            f"Telegram auth expired for user {user_id}. Age: {age_seconds}s",
            extra={"user_id": user_id, "age_seconds": age_seconds},
        )
        raise AuthenticationError(
            f"Authentication expired ({age_seconds} seconds old). Please log in again."
        )

    if age_seconds < -60:  # Allow 1 minute clock skew
        logger.warning(
            f"Telegram auth timestamp in future for user {user_id}. Skew: {-age_seconds}s",
            extra={"user_id": user_id, "skew_seconds": -age_seconds},
        )
        raise AuthenticationError("Authentication timestamp is in the future. Check device clock.")

    # Build data check string according to Telegram spec
    data_check_arr = [f"auth_date={auth_date}", f"id={user_id}"]

    if first_name:
        data_check_arr.append(f"first_name={first_name}")
    if last_name:
        data_check_arr.append(f"last_name={last_name}")
    if photo_url:
        data_check_arr.append(f"photo_url={photo_url}")
    if username:
        data_check_arr.append(f"username={username}")

    # Sort alphabetically (required by Telegram)
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)

    # Get bot token
    try:
        bot_token = Config.get("BOT_TOKEN")
    except ValueError as err:
        logger.error("BOT_TOKEN not configured - cannot verify Telegram auth")
        raise ConfigurationError(
            "Server misconfiguration: BOT_TOKEN is not set.", config_key="BOT_TOKEN"
        ) from err

    if not bot_token:
        logger.error("BOT_TOKEN is empty - cannot verify Telegram auth")
        raise ConfigurationError(
            "Server misconfiguration: BOT_TOKEN is empty.", config_key="BOT_TOKEN"
        )

    # Compute secret key: SHA256(bot_token)
    secret_key = hashlib.sha256(bot_token.encode()).digest()

    # Compute HMAC-SHA256
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    # Verify hash matches using constant-time comparison
    if not hmac.compare_digest(computed_hash, auth_hash):
        logger.warning(
            f"Invalid Telegram auth hash for user {user_id}",
            extra={"user_id": user_id, "username": username},
        )
        raise AuthenticationError("Invalid authentication hash. Please try logging in again.")

    # Verify user is in whitelist
    allowed_ids = Config.get_allowed_user_ids()
    if user_id not in allowed_ids:
        logger.warning(
            f"User {user_id} not in whitelist",
            extra={"user_id": user_id, "username": username},
        )
        raise AuthorizationError("User not authorized. Contact administrator to request access.")

    logger.info(
        f"Telegram auth verified for user {user_id}",
        extra={"user_id": user_id, "username": username},
    )

    return True


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
) -> tuple[str, int]:
    """Create and persist JWT refresh token.

    Returns:
        Tuple of (token_string, session_id) where session_id is the refresh token record ID.
    """
    token = create_token(user_id, "refresh", client_id=client_id)

    # Persist token hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    session_id = await auth_repo.async_create_refresh_token(
        user_id=user_id,
        token_hash=token_hash,
        client_id=client_id,
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
    )

    return token, session_id


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


def _ensure_secret_login_enabled() -> None:
    if not _get_auth_config().secret_login_enabled:
        raise FeatureDisabledError("secret-login", "Secret-key login is disabled")


def _ensure_user_allowed(user_id: int) -> None:
    allowed_ids = Config.get_allowed_user_ids()
    if user_id not in allowed_ids:
        logger.warning(
            "User not authorized for secret login",
            extra={"user_id": user_id},
        )
        raise AuthorizationError("User not authorized. Contact administrator to request access.")


async def _require_owner(user: dict) -> dict:
    """Verify user is an owner and return user data dict."""
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user_record = await user_repo.async_get_user_by_telegram_id(user["user_id"])
    if not user_record or not user_record.get("is_owner"):
        raise AuthorizationError("Owner permissions required")
    return user_record


def _format_dt(dt_value: datetime | None) -> str | None:
    if dt_value is None:
        return None
    if dt_value.tzinfo:
        return dt_value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return dt_value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


async def _get_target_user(user_id: int, username: str | None = None) -> dict:
    """Get or create target user, returning user data dict."""
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user_data, _ = await user_repo.async_get_or_create_user(
        user_id,
        username=username,
        is_owner=True,
    )
    # TODO: Update username if changed (requires async_update_user method)
    # For now, username update on existing users is skipped
    return user_data


def _validate_secret_value(secret: str, *, context: str = "login") -> str:
    """Validate provided secret length."""
    cfg = _get_auth_config()
    cleaned = secret.strip()
    length = len(cleaned)
    if length < cfg.secret_min_length or length > cfg.secret_max_length:
        if context == "login":
            raise AuthenticationError("Invalid secret length")
        raise ValidationError("Invalid secret length", details={"field": "secret"})
    return cleaned


def _hash_secret(secret: str, salt: str) -> str:
    pepper = _get_secret_pepper().encode()
    payload = f"{salt}:{secret}".encode()
    return hmac.new(pepper, payload, hashlib.sha256).hexdigest()


def _generate_secret_value() -> str:
    cfg = _get_auth_config()
    target_len = max(cfg.secret_min_length, 32)
    while True:
        candidate = secrets.token_urlsafe(target_len)
        if len(candidate) >= cfg.secret_min_length:
            break
    if len(candidate) > cfg.secret_max_length:
        candidate = candidate[: cfg.secret_max_length]
    return candidate


def _serialize_secret(record: dict) -> ClientSecretInfo:
    """Serialize a client secret dict to ClientSecretInfo."""

    def _fmt(dt_value: datetime | str | None) -> str | None:
        if dt_value is None:
            return None
        if isinstance(dt_value, str):
            return dt_value if dt_value.endswith("Z") else dt_value + "Z"
        return dt_value.isoformat() + "Z"

    # Handle user_id - may be nested dict or direct value
    user_id = record.get("user_id")
    if user_id is None and isinstance(record.get("user"), dict):
        user_id = record["user"].get("telegram_user_id")
    elif user_id is None:
        user_id = record.get("user")

    return ClientSecretInfo(
        id=record.get("id", 0),
        user_id=user_id or 0,
        client_id=record.get("client_id", ""),
        status=record.get("status", "unknown"),
        label=record.get("label"),
        description=record.get("description"),
        expires_at=_fmt(record.get("expires_at")),
        last_used_at=_fmt(record.get("last_used_at")),
        failed_attempts=record.get("failed_attempts") or 0,
        locked_until=_fmt(record.get("locked_until")),
        created_at=_fmt(record.get("created_at")) or "",
        updated_at=_fmt(record.get("updated_at")) or "",
    )


async def _revoke_active_secrets(user_id: int, client_id: str) -> None:
    """Revoke all active secrets for a user/client pair."""
    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    await auth_repo.async_revoke_active_secrets(user_id, client_id)


async def _check_expired(record: dict) -> None:
    """Check if secret has expired and update status if so."""
    now = _utcnow_naive()
    expires_at = record.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00")).replace(
                tzinfo=None
            )
        if expires_at < now:
            auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
            await auth_repo.async_update_client_secret(record["id"], status="expired")
            raise AuthenticationError("Secret has expired")


async def _handle_failed_attempt(record: dict) -> None:
    """Increment failed attempts and potentially lock the secret."""
    cfg = _get_auth_config()
    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    await auth_repo.async_increment_failed_attempts(
        record["id"],
        max_attempts=cfg.secret_max_failed_attempts,
        lockout_minutes=cfg.secret_lockout_minutes,
    )


async def _reset_failed_attempts(record: dict) -> None:
    """Reset failed attempts and unlock secret."""
    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    await auth_repo.async_reset_failed_attempts(record["id"])


async def _build_secret_record(
    user_id: int,
    client_id: str,
    *,
    provided_secret: str | None,
    label: str | None,
    description: str | None,
    expires_at: datetime | None,
) -> tuple[str, dict]:
    """Build and create a client secret record.

    Returns:
        Tuple of (secret_value, record_dict).
    """
    secret_value = (
        _validate_secret_value(provided_secret, context="create")
        if provided_secret
        else _generate_secret_value()
    )
    salt = secrets.token_hex(16)
    secret_hash = _hash_secret(secret_value, salt)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    record_id = await auth_repo.async_create_client_secret(
        user_id=user_id,
        client_id=client_id,
        secret_hash=secret_hash,
        secret_salt=salt,
        status="active",
        label=label,
        description=description,
        expires_at=expires_at,
    )

    # Fetch the created record to return
    record = await auth_repo.async_get_client_secret_by_id(record_id)
    return secret_value, record or {}


async def _ensure_user(user_id: int) -> dict:
    """Ensure user exists and return user data dict."""
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user = await user_repo.async_get_user_by_telegram_id(user_id)
    if not user:
        raise ResourceNotFoundError("User", user_id)
    return user


# TODO: User link nonce operations require a dedicated async method in user repository
# For now, these remain as stubs that will need direct model access or repository extension
async def _set_link_nonce(user_id: int, nonce: str, expires_at: datetime) -> None:
    """Set link nonce for a user. TODO: Implement via repository."""
    # This requires extending SqliteUserRepositoryAdapter with async_set_link_nonce
    from app.db.models import User as UserModel

    def _set() -> None:
        user = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
        if user:
            user.link_nonce = nonce
            user.link_nonce_expires_at = _coerce_naive(expires_at)
            user.save()

    import asyncio

    await asyncio.to_thread(_set)


async def _clear_link_nonce(user_id: int) -> None:
    """Clear link nonce for a user. TODO: Implement via repository."""
    from app.db.models import User as UserModel

    def _clear() -> None:
        user = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
        if user:
            user.link_nonce = None
            user.link_nonce_expires_at = None
            user.save()

    import asyncio

    await asyncio.to_thread(_clear)


def _link_status_payload(user: dict) -> TelegramLinkStatus:
    """Build link status payload from user dict."""
    linked = user.get("linked_telegram_user_id") is not None
    return TelegramLinkStatus(
        linked=linked,
        telegram_user_id=user.get("linked_telegram_user_id") if linked else None,
        username=user.get("linked_telegram_username") if linked else None,
        photo_url=user.get("linked_telegram_photo_url") if linked else None,
        first_name=user.get("linked_telegram_first_name") if linked else None,
        last_name=user.get("linked_telegram_last_name") if linked else None,
        linked_at=_format_dt(user.get("linked_at")),
        link_nonce_expires_at=_format_dt(user.get("link_nonce_expires_at")),
        link_nonce=user.get("link_nonce"),
    )


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


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get current authenticated user.

    Validates JWT token and returns user data.

    Raises:
        TokenExpiredError: Access token has expired (401)
        TokenInvalidError: Token is malformed (401)
        TokenWrongTypeError: Not an access token (401)
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


@router.post("/telegram-login")
async def telegram_login(login_data: TelegramLoginRequest):
    """
    Exchange Telegram authentication data for JWT tokens.

    Verifies Telegram auth hash using HMAC-SHA256 and returns access + refresh tokens.

    The authentication data must come from Telegram Login Widget and include:
    - id: Telegram user ID
    - hash: HMAC-SHA256 hash of auth data
    - auth_date: Unix timestamp of authentication
    - client_id: Client application ID
    - Optional: username, first_name, last_name, photo_url
    """
    try:
        # Validate client_id FIRST (before any other processing)
        validate_client_id(login_data.client_id)

        # Verify Telegram auth (will raise HTTPException if invalid)
        verify_telegram_auth(
            user_id=login_data.telegram_user_id,
            auth_hash=login_data.auth_hash,
            auth_date=login_data.auth_date,
            username=login_data.username,
            first_name=login_data.first_name,
            last_name=login_data.last_name,
            photo_url=login_data.photo_url,
        )

        # Get or create user using repository
        user_repo = SqliteUserRepositoryAdapter(database_proxy)
        user, created = await user_repo.async_get_or_create_user(
            login_data.telegram_user_id,
            username=login_data.username,
            is_owner=True,
        )

        # TODO: Update username if changed (requires async_update_user method)
        user_id = user.get("telegram_user_id", login_data.telegram_user_id)
        username = user.get("username", login_data.username)

        # Generate tokens with client_id
        access_token = create_access_token(user_id, username, login_data.client_id)
        refresh_token, session_id = await create_refresh_token(user_id, login_data.client_id)

        logger.info(
            f"User {user_id} logged in from client {login_data.client_id}",
            extra={
                "user_id": user_id,
                "username": username,
                "client_id": login_data.client_id,
                "created": created,
            },
        )

        tokens = TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            token_type="Bearer",
        )
        return success_response(AuthTokensResponse(tokens=tokens, session_id=session_id))

    except (
        AuthenticationError,
        AuthorizationError,
        ConfigurationError,
        ValidationError,
    ):
        # Re-raise structured exceptions from verify_telegram_auth or validate_client_id
        raise
    except Exception as e:
        logger.error(f"Login failed for user {login_data.telegram_user_id}: {e}", exc_info=True)
        raise ProcessingError("Authentication failed. Please try again.") from e


@router.post("/secret-login")
async def secret_login(login_data: SecretLoginRequest):
    """Exchange a pre-registered client secret for JWT tokens."""
    _ensure_secret_login_enabled()
    validate_client_id(login_data.client_id)
    _ensure_user_allowed(login_data.user_id)
    now = _utcnow_naive()

    # Get user via repository
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user = await user_repo.async_get_user_by_telegram_id(login_data.user_id)
    if not user:
        raise ResourceNotFoundError("User", login_data.user_id)

    # Get client secret via repository
    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    secret_record = await auth_repo.async_get_client_secret(
        login_data.user_id, login_data.client_id
    )

    if not secret_record:
        raise AuthenticationError("Invalid credentials")

    if secret_record.get("status") == "revoked":
        raise AuthenticationError("Secret has been revoked")

    if secret_record.get("status") == "locked":
        locked_until = secret_record.get("locked_until")
        if locked_until:
            if isinstance(locked_until, str):
                locked_until = datetime.fromisoformat(locked_until.replace("Z", "+00:00")).replace(
                    tzinfo=None
                )
            if locked_until < now:
                await auth_repo.async_update_client_secret(secret_record["id"], status="active")
                await _reset_failed_attempts(secret_record)
            else:
                raise AuthorizationError("Secret is temporarily locked")
        else:
            raise AuthorizationError("Secret is temporarily locked")

    await _check_expired(secret_record)

    provided_secret = _validate_secret_value(login_data.secret, context="login")
    expected_hash = _hash_secret(provided_secret, secret_record.get("secret_salt", ""))

    if not hmac.compare_digest(expected_hash, secret_record.get("secret_hash", "")):
        await _handle_failed_attempt(secret_record)
        raise AuthenticationError("Invalid credentials")

    await _reset_failed_attempts(secret_record)
    await auth_repo.async_update_client_secret(
        secret_record["id"],
        last_used_at=now,
        status="active",
    )

    # TODO: Update username if changed (requires async_update_user method)
    user_id = user.get("telegram_user_id", login_data.user_id)
    username = user.get("username", login_data.username)

    access_token = create_access_token(user_id, username, login_data.client_id)
    refresh_token, session_id = await create_refresh_token(user_id, login_data.client_id)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )

    logger.info(
        "secret_login_success",
        extra={
            "user_id": user_id,
            "client_id": login_data.client_id,
            "session_id": session_id,
        },
    )

    return success_response(AuthTokensResponse(tokens=tokens, session_id=session_id))


@router.post("/refresh")
async def refresh_access_token(refresh_data: RefreshTokenRequest):
    """
    Refresh an expired access token using a refresh token.

    Returns:
        New access token on success

    Raises:
        TokenExpiredError: Refresh token has expired (401)
        TokenInvalidError: Token is malformed (401)
        TokenWrongTypeError: Not a refresh token (401)
        TokenRevokedError: Refresh token was revoked (401)
        ResourceNotFoundError: User not found (404)
    """
    from app.api.exceptions import ResourceNotFoundError, TokenInvalidError, TokenRevokedError

    # Decode and validate refresh token
    payload = decode_token(refresh_data.refresh_token, expected_type="refresh")

    user_id = payload.get("user_id")
    if not user_id:
        raise TokenInvalidError("Missing user_id in token payload")

    # Validate client_id from refresh token
    client_id = payload.get("client_id")
    validate_client_id(client_id)

    # Verify refresh token is not revoked
    token_hash = hashlib.sha256(refresh_data.refresh_token.encode()).hexdigest()
    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    refresh_token_record = await auth_repo.async_get_refresh_token_by_hash(token_hash)
    if not refresh_token_record:
        raise TokenInvalidError("Refresh token is not recognized")
    if refresh_token_record.get("is_revoked"):
        raise TokenRevokedError()

    # Get user
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user = await user_repo.async_get_user_by_telegram_id(user_id)
    if not user:
        raise ResourceNotFoundError("User", user_id)

    # Update session metadata and generate new access token with same client_id
    await auth_repo.async_update_refresh_token_last_used(refresh_token_record["id"])
    access_token = create_access_token(
        user.get("telegram_user_id", user_id),
        user.get("username"),
        client_id,
    )

    logger.info(
        "token_refreshed",
        extra={"user_id": user_id, "client_id": client_id},
    )

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=None,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )
    return success_response(AuthTokensResponse(tokens=tokens))


@router.post("/secret-keys")
async def create_secret_key(payload: SecretKeyCreateRequest, user=Depends(get_current_user)):
    """Create or register a client secret for a user (owner-only)."""
    _ensure_secret_login_enabled()
    admin_user = await _require_owner(user)
    validate_client_id(payload.client_id)
    _ensure_user_allowed(payload.user_id)

    target_user = await _get_target_user(payload.user_id, payload.username)
    target_user_id = target_user.get("telegram_user_id", payload.user_id)

    await _revoke_active_secrets(target_user_id, payload.client_id)
    secret_value, record = await _build_secret_record(
        target_user_id,
        payload.client_id,
        provided_secret=payload.secret,
        label=payload.label,
        description=payload.description,
        expires_at=_coerce_naive(payload.expires_at),
    )

    logger.info(
        "secret_key_created",
        extra={
            "created_by": admin_user.get("telegram_user_id"),
            "user_id": target_user_id,
            "client_id": payload.client_id,
            "label": payload.label,
        },
    )

    return success_response(
        SecretKeyCreateResponse(secret=secret_value, key=_serialize_secret(record))
    )


@router.post("/secret-keys/{key_id}/rotate")
async def rotate_secret_key(
    key_id: int, payload: SecretKeyRotateRequest, user=Depends(get_current_user)
):
    """Rotate an existing client secret (owner-only)."""
    _ensure_secret_login_enabled()
    admin_user = await _require_owner(user)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    record = await auth_repo.async_get_client_secret_by_id(key_id)
    if not record:
        raise ResourceNotFoundError("Secret key", key_id)

    # Get user_id from nested user dict, direct field, or user as int
    record_user_id = record.get("user_id")
    if record_user_id is None:
        user_field = record.get("user")
        if isinstance(user_field, dict):
            record_user_id = user_field.get("telegram_user_id")
        elif isinstance(user_field, int):
            record_user_id = user_field

    _ensure_user_allowed(record_user_id)
    validate_client_id(record.get("client_id", ""))

    new_secret_value = (
        _validate_secret_value(payload.secret, context="create")
        if payload.secret
        else _generate_secret_value()
    )
    new_salt = secrets.token_hex(16)
    new_hash = _hash_secret(new_secret_value, new_salt)

    await auth_repo.async_update_client_secret(
        key_id,
        secret_salt=new_salt,
        secret_hash=new_hash,
        status="active",
        failed_attempts=0,
        locked_until=None,
        expires_at=_coerce_naive(payload.expires_at) or record.get("expires_at"),
        label=payload.label if payload.label is not None else record.get("label"),
        description=(
            payload.description if payload.description is not None else record.get("description")
        ),
        last_used_at=None,
    )

    # Fetch updated record
    updated_record = await auth_repo.async_get_client_secret_by_id(key_id)

    logger.info(
        "secret_key_rotated",
        extra={
            "rotated_by": admin_user.get("telegram_user_id"),
            "user_id": record_user_id,
            "client_id": record.get("client_id"),
            "key_id": key_id,
        },
    )

    return success_response(
        SecretKeyCreateResponse(
            secret=new_secret_value, key=_serialize_secret(updated_record or {})
        )
    )


@router.post("/secret-keys/{key_id}/revoke")
async def revoke_secret_key(
    key_id: int, payload: SecretKeyRevokeRequest | None = None, user=Depends(get_current_user)
):
    """Revoke an existing client secret (owner-only)."""
    _ensure_secret_login_enabled()
    admin_user = await _require_owner(user)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    record = await auth_repo.async_get_client_secret_by_id(key_id)
    if not record:
        raise ResourceNotFoundError("Secret key", key_id)

    # Get user_id from nested user dict, direct field, or user as int
    record_user_id = record.get("user_id")
    if record_user_id is None:
        user_field = record.get("user")
        if isinstance(user_field, dict):
            record_user_id = user_field.get("telegram_user_id")
        elif isinstance(user_field, int):
            record_user_id = user_field

    _ensure_user_allowed(record_user_id)

    await auth_repo.async_update_client_secret(
        key_id,
        status="revoked",
        failed_attempts=0,
        locked_until=None,
    )

    # Fetch updated record
    updated_record = await auth_repo.async_get_client_secret_by_id(key_id)

    logger.info(
        "secret_key_revoked",
        extra={
            "revoked_by": admin_user.get("telegram_user_id"),
            "user_id": record_user_id,
            "client_id": record.get("client_id"),
            "key_id": key_id,
            "reason": payload.reason if payload else None,
        },
    )

    return success_response(SecretKeyActionResponse(key=_serialize_secret(updated_record or {})))


@router.get("/secret-keys")
async def list_secret_keys(
    user=Depends(get_current_user),
    user_id: int | None = None,
    client_id: str | None = None,
    status: str | None = None,
):
    """List stored client secrets (owner-only)."""
    _ensure_secret_login_enabled()
    await _require_owner(user)

    if user_id is not None:
        _ensure_user_allowed(user_id)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    records = await auth_repo.async_list_client_secrets(
        user_id=user_id,
        client_id=client_id,
        status=status,
    )

    keys = [_serialize_secret(rec) for rec in records]
    return success_response(SecretKeyListResponse(keys=keys))


@router.get("/me")
async def get_current_user_info(user=Depends(get_current_user)):
    """Get current authenticated user information."""
    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user_record, _ = await user_repo.async_get_or_create_user(
        user["user_id"],
        username=user.get("username"),
        is_owner=False,
    )

    # Format created_at from dict
    created_at_value = user_record.get("created_at")
    if created_at_value:
        if isinstance(created_at_value, str):
            created_at_str = (
                created_at_value if created_at_value.endswith("Z") else created_at_value + "Z"
            )
        else:
            created_at_str = created_at_value.isoformat() + "Z"
    else:
        created_at_str = ""

    return success_response(
        UserInfo(
            user_id=user["user_id"],
            username=user.get("username") or "",
            client_id=user["client_id"],
            is_owner=user_record.get("is_owner", False),
            created_at=created_at_str,
        )
    )


@router.get("/me/telegram")
async def get_telegram_link_status(user=Depends(get_current_user)):
    """Fetch current Telegram link status."""
    user_record = await _ensure_user(user["user_id"])
    return success_response(_link_status_payload(user_record))


@router.delete("/me")
async def delete_account(user=Depends(get_current_user)):
    """Delete the current user account and all associated data."""
    user_id = user["user_id"]
    # Verify user exists
    await _ensure_user(user_id)

    # Delete all associated data
    # TODO: Implement via repository with proper cascade delete
    # For now, use direct model access
    import asyncio

    from app.db.models import User as UserModel

    def _delete() -> None:
        user_record = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
        if user_record:
            user_record.delete_instance(recursive=True)

    try:
        await asyncio.to_thread(_delete)
        logger.info(f"User {user_id} deleted their account")
        return success_response({"success": True})
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}", exc_info=True)
        raise ProcessingError("Failed to delete account") from e


@router.post("/apple-login")
async def apple_login(login_data: AppleLoginRequest):
    """Exchange Apple authentication data for JWT tokens.

    Verifies the Apple ID token cryptographically using Apple's public keys,
    then creates a session for the authenticated user.
    """
    logger.info(f"Apple login attempt for client {login_data.client_id}")

    # Validate client_id before any processing
    validate_client_id(login_data.client_id)

    # Verify the Apple ID token cryptographically
    claims = verify_apple_id_token(login_data.id_token, login_data.client_id)

    # Extract user identifier from verified claims
    apple_sub = claims.get("sub")
    if not apple_sub:
        raise AuthenticationError("Apple ID token missing 'sub' claim")

    # Derive consistent numeric user ID from the 'sub' claim
    apple_user_id = _derive_user_id_from_sub("apple", apple_sub)

    # Verify user is in whitelist (optional - can be removed for open registration)
    allowed_ids = Config.get_allowed_user_ids()
    if allowed_ids and apple_user_id not in allowed_ids:
        logger.warning(
            "User not authorized via Apple login",
            extra={"user_id": apple_user_id, "apple_sub": apple_sub},
        )
        raise AuthorizationError("User not authorized. Contact administrator to request access.")

    # Get or create user
    # Use email from claims if available, otherwise construct from name claims
    display_name = None
    if login_data.given_name or login_data.family_name:
        name_parts = [login_data.given_name, login_data.family_name]
        display_name = " ".join(p for p in name_parts if p)
    email = claims.get("email")

    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user, created = await user_repo.async_get_or_create_user(
        apple_user_id,
        username=display_name or email or f"apple_{apple_user_id}",
        is_owner=False,
    )

    if created:
        logger.info(
            f"Created new user via Apple login: {apple_user_id}",
            extra={"email": email, "apple_sub": apple_sub},
        )

    # Generate tokens
    user_id = user.get("telegram_user_id", apple_user_id)
    username = user.get("username")
    access_token = create_access_token(user_id, username, login_data.client_id)
    refresh_token, session_id = await create_refresh_token(user_id, login_data.client_id)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )

    return success_response(AuthTokensResponse(tokens=tokens, session_id=session_id))


@router.post("/google-login")
async def google_login(login_data: GoogleLoginRequest):
    """Exchange Google authentication data for JWT tokens.

    Verifies the Google ID token cryptographically using Google's public keys,
    then creates a session for the authenticated user.
    """
    logger.info(f"Google login attempt for client {login_data.client_id}")

    # Validate client_id before any processing
    validate_client_id(login_data.client_id)

    # Verify the Google ID token cryptographically
    claims = verify_google_id_token(login_data.id_token, login_data.client_id)

    # Extract user identifier from verified claims
    google_sub = claims.get("sub")
    if not google_sub:
        raise AuthenticationError("Google ID token missing 'sub' claim")

    # Derive consistent numeric user ID from the 'sub' claim
    google_user_id = _derive_user_id_from_sub("google", google_sub)

    # Verify user is in whitelist (optional - can be removed for open registration)
    allowed_ids = Config.get_allowed_user_ids()
    if allowed_ids and google_user_id not in allowed_ids:
        logger.warning(
            "User not authorized via Google login",
            extra={"user_id": google_user_id, "google_sub": google_sub},
        )
        raise AuthorizationError("User not authorized. Contact administrator to request access.")

    # Get or create user
    email = claims.get("email")
    name = claims.get("name")  # Google provides full name in 'name' claim

    user_repo = SqliteUserRepositoryAdapter(database_proxy)
    user, created = await user_repo.async_get_or_create_user(
        google_user_id,
        username=name or email or f"google_{google_user_id}",
        is_owner=False,
    )

    if created:
        logger.info(
            f"Created new user via Google login: {google_user_id}",
            extra={"email": email, "google_sub": google_sub},
        )

    # Generate tokens
    user_id = user.get("telegram_user_id", google_user_id)
    username = user.get("username")
    access_token = create_access_token(user_id, username, login_data.client_id)
    refresh_token, session_id = await create_refresh_token(user_id, login_data.client_id)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )

    return success_response(AuthTokensResponse(tokens=tokens, session_id=session_id))


@router.post("/me/telegram/link")
async def begin_telegram_link(user=Depends(get_current_user)):
    """Begin linking by issuing a nonce."""
    await _ensure_user(user["user_id"])
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    nonce = secrets.token_urlsafe(32)
    await _set_link_nonce(user["user_id"], nonce, expires_at)
    return success_response(
        TelegramLinkBeginResponse(nonce=nonce, expires_at=_format_dt(expires_at) or "")
    )


class TelegramLinkCompleteRequest(TelegramLoginRequest):
    """Complete linking using Telegram login payload + nonce."""

    nonce: str


@router.post("/me/telegram/complete")
async def complete_telegram_link(
    payload: TelegramLinkCompleteRequest, user=Depends(get_current_user)
):
    """Complete Telegram linking by validating nonce and Telegram login payload."""
    # TODO: Implement full async link completion via repository
    # This is complex as it requires updating multiple linked_telegram_* fields
    import asyncio

    from app.db.models import User as UserModel

    user_id = user["user_id"]

    def _get_user() -> UserModel | None:
        return UserModel.get_or_none(UserModel.telegram_user_id == user_id)

    user_record = await asyncio.to_thread(_get_user)
    if not user_record:
        raise ResourceNotFoundError("User", user_id)

    if not user_record.link_nonce or not user_record.link_nonce_expires_at:
        raise ValidationError("Linking not initiated", details={"field": "nonce"})

    now = _utcnow_naive()
    if payload.nonce != user_record.link_nonce:
        raise ValidationError("Invalid link nonce", details={"field": "nonce"})
    if user_record.link_nonce_expires_at < now:
        raise ValidationError("Link nonce expired", details={"field": "nonce"})

    verify_telegram_auth(
        user_id=payload.telegram_user_id,
        auth_hash=payload.auth_hash,
        auth_date=payload.auth_date,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        photo_url=payload.photo_url,
    )

    def _update_link() -> None:
        user_rec = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
        if user_rec:
            user_rec.linked_telegram_user_id = payload.telegram_user_id
            user_rec.linked_telegram_username = payload.username
            user_rec.linked_telegram_photo_url = payload.photo_url
            user_rec.linked_telegram_first_name = payload.first_name
            user_rec.linked_telegram_last_name = payload.last_name
            user_rec.linked_at = now
            user_rec.link_nonce = None
            user_rec.link_nonce_expires_at = None
            user_rec.save()

    await asyncio.to_thread(_update_link)

    # Re-fetch for response
    updated_user = await _ensure_user(user_id)

    logger.info(
        "telegram_linked",
        extra={
            "user_id": user_id,
            "linked_telegram_user_id": payload.telegram_user_id,
            "username": payload.username,
        },
    )

    return success_response(_link_status_payload(updated_user))


@router.delete("/me/telegram")
async def unlink_telegram(user=Depends(get_current_user)):
    """Unlink Telegram account."""
    # TODO: Implement full async unlink via repository
    import asyncio

    from app.db.models import User as UserModel

    user_id = user["user_id"]

    def _unlink() -> None:
        user_record = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
        if user_record:
            user_record.linked_telegram_user_id = None
            user_record.linked_telegram_username = None
            user_record.linked_telegram_photo_url = None
            user_record.linked_telegram_first_name = None
            user_record.linked_telegram_last_name = None
            user_record.linked_at = None
            user_record.link_nonce = None
            user_record.link_nonce_expires_at = None
            user_record.save()

    await asyncio.to_thread(_unlink)

    # Re-fetch for response
    updated_user = await _ensure_user(user_id)

    logger.info(
        "telegram_unlinked",
        extra={
            "user_id": user_id,
        },
    )

    return success_response(_link_status_payload(updated_user))


@router.post("/logout")
async def logout(
    request: RefreshTokenRequest,
    _: dict = Depends(get_current_user),  # Require authentication (optional, but good for security)
):
    """
    Logout by revoking the specific refresh token.
    """
    token = request.refresh_token
    try:
        # Allow logout even if token expired; we hash and look up so garbage won't be found
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
        revoked = await auth_repo.async_revoke_refresh_token(token_hash)

        if revoked:
            logger.info("Revoked refresh token", extra={"token_hash": token_hash[:8] + "..."})

    except Exception as e:
        logger.warning(f"Logout failed: {e}")
        # We still return success to the client

    return success_response({"message": "Logged out successfully"})


class SessionInfo(BaseModel):
    id: int
    client_id: str | None
    device_info: str | None
    ip_address: str | None
    last_used_at: str | None
    created_at: str
    is_current: bool = False


@router.get("/sessions")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    List active sessions for the current user.
    """
    user_id = current_user["user_id"]
    now = datetime.now(UTC)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    sessions = await auth_repo.async_list_active_sessions(user_id, now)

    formatted_sessions = []
    for s in sessions:
        last_used = s.get("last_used_at")
        if last_used and hasattr(last_used, "isoformat"):
            last_used = last_used.isoformat() + "Z"
        elif last_used:
            # Already a string or something else
            last_used = str(last_used) if str(last_used).endswith("Z") else str(last_used) + "Z"

        created = s.get("created_at")
        if created and hasattr(created, "isoformat"):
            created = created.isoformat() + "Z"
        else:
            created = str(created) if str(created).endswith("Z") else str(created) + "Z"

        formatted_sessions.append(
            SessionInfo(
                id=s.get("id", 0),
                client_id=s.get("client_id"),
                device_info=s.get("device_info"),
                ip_address=s.get("ip_address"),
                last_used_at=last_used,
                created_at=created,
            )
        )

    return success_response({"sessions": formatted_sessions})

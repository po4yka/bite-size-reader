"""
Authentication endpoints and utilities.
"""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
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
from app.db.models import ClientSecret, RefreshToken, User

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


def create_refresh_token(
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

    refresh_token_record = RefreshToken.create(
        user=user_id,
        token_hash=token_hash,
        client_id=client_id,
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
        is_revoked=False,
    )

    return token, refresh_token_record.id


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


def _require_owner(user: dict) -> User:
    user_record = User.select().where(User.telegram_user_id == user["user_id"]).first()
    if not user_record or not user_record.is_owner:
        raise AuthorizationError("Owner permissions required")
    return user_record


def _format_dt(dt_value: datetime | None) -> str | None:
    if dt_value is None:
        return None
    if dt_value.tzinfo:
        return dt_value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return dt_value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _get_target_user(user_id: int, username: str | None = None) -> User:
    user, created = User.get_or_create(
        telegram_user_id=user_id,
        defaults={"username": username, "is_owner": True},
    )
    if not created and username and user.username != username:
        user.username = username
        user.save()
    return user


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


def _serialize_secret(record: ClientSecret) -> ClientSecretInfo:
    def _fmt(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.isoformat() + "Z"

    return ClientSecretInfo(
        id=record.id,
        user_id=record.user.telegram_user_id if isinstance(record.user, User) else record.user_id,
        client_id=record.client_id,
        status=record.status,
        label=record.label,
        description=record.description,
        expires_at=_fmt(record.expires_at),
        last_used_at=_fmt(record.last_used_at),
        failed_attempts=record.failed_attempts or 0,
        locked_until=_fmt(record.locked_until),
        created_at=_fmt(record.created_at) or "",
        updated_at=_fmt(record.updated_at) or "",
    )


def _revoke_active_secrets(user: User, client_id: str) -> None:
    active = (
        ClientSecret.select()
        .where(
            (ClientSecret.user == user),
            (ClientSecret.client_id == client_id),
            (ClientSecret.status == "active"),
        )
        .execute()
    )
    for record in active:
        record.status = "revoked"
        record.failed_attempts = 0
        record.locked_until = None
        record.save()


def _check_expired(record: ClientSecret) -> None:
    now = _utcnow_naive()
    if record.expires_at and record.expires_at < now:
        record.status = "expired"
        record.save()
        raise AuthenticationError("Secret has expired")


def _handle_failed_attempt(record: ClientSecret) -> None:
    cfg = _get_auth_config()
    record.failed_attempts = (record.failed_attempts or 0) + 1
    if record.failed_attempts >= cfg.secret_max_failed_attempts:
        record.status = "locked"
        record.locked_until = _utcnow_naive() + timedelta(minutes=cfg.secret_lockout_minutes)
    record.save()


def _reset_failed_attempts(record: ClientSecret) -> None:
    record.failed_attempts = 0
    record.locked_until = None
    record.save()


def _build_secret_record(
    user: User,
    client_id: str,
    *,
    provided_secret: str | None,
    label: str | None,
    description: str | None,
    expires_at: datetime | None,
) -> tuple[str, ClientSecret]:
    secret_value = (
        _validate_secret_value(provided_secret, context="create")
        if provided_secret
        else _generate_secret_value()
    )
    salt = secrets.token_hex(16)
    secret_hash = _hash_secret(secret_value, salt)
    record = ClientSecret.create(
        user=user,
        client_id=client_id,
        secret_hash=secret_hash,
        secret_salt=salt,
        status="active",
        label=label,
        description=description,
        expires_at=expires_at,
        failed_attempts=0,
        locked_until=None,
    )
    return secret_value, record


def _ensure_user(user_id: int) -> User:
    user = User.select().where(User.telegram_user_id == user_id).first()
    if not user:
        raise ResourceNotFoundError("User", user_id)
    return user


def _set_link_nonce(user: User, nonce: str, expires_at: datetime) -> None:
    user.link_nonce = nonce
    user.link_nonce_expires_at = _coerce_naive(expires_at)
    user.save()


def _clear_link_nonce(user: User) -> None:
    user.link_nonce = None
    user.link_nonce_expires_at = None
    user.save()


def _link_status_payload(user: User) -> TelegramLinkStatus:
    linked = user.linked_telegram_user_id is not None
    return TelegramLinkStatus(
        linked=linked,
        telegram_user_id=user.linked_telegram_user_id if linked else None,
        username=user.linked_telegram_username if linked else None,
        photo_url=user.linked_telegram_photo_url if linked else None,
        first_name=user.linked_telegram_first_name if linked else None,
        last_name=user.linked_telegram_last_name if linked else None,
        linked_at=_format_dt(user.linked_at),
        link_nonce_expires_at=_format_dt(user.link_nonce_expires_at),
        link_nonce=user.link_nonce,
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

    # Verify user is still in whitelist
    allowed_ids = Config.get_allowed_user_ids()
    if user_id not in allowed_ids:
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

        # Get or create user
        user, created = User.get_or_create(
            telegram_user_id=login_data.telegram_user_id,
            defaults={"username": login_data.username, "is_owner": True},
        )

        # Update username if changed
        if not created and login_data.username and user.username != login_data.username:
            user.username = login_data.username
            user.save()
            logger.info(
                f"Updated username for user {user.telegram_user_id}: {user.username}",
                extra={"user_id": user.telegram_user_id},
            )

        # Generate tokens with client_id
        access_token = create_access_token(
            user.telegram_user_id, user.username, login_data.client_id
        )
        refresh_token, session_id = create_refresh_token(
            user.telegram_user_id, login_data.client_id
        )

        logger.info(
            f"User {user.telegram_user_id} logged in from client {login_data.client_id}",
            extra={
                "user_id": user.telegram_user_id,
                "username": user.username,
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

    user = User.select().where(User.telegram_user_id == login_data.user_id).first()
    if not user:
        raise ResourceNotFoundError("User", login_data.user_id)

    secret_record = (
        ClientSecret.select()
        .where(
            (ClientSecret.user == user),
            (ClientSecret.client_id == login_data.client_id),
        )
        .order_by(ClientSecret.created_at.desc())
        .first()
    )

    if not secret_record:
        raise AuthenticationError("Invalid credentials")

    if secret_record.status == "revoked":
        raise AuthenticationError("Secret has been revoked")

    if secret_record.status == "locked":
        if secret_record.locked_until and secret_record.locked_until < now:
            secret_record.status = "active"
            _reset_failed_attempts(secret_record)
        else:
            raise AuthorizationError("Secret is temporarily locked")

    _check_expired(secret_record)

    provided_secret = _validate_secret_value(login_data.secret, context="login")
    expected_hash = _hash_secret(provided_secret, secret_record.secret_salt)

    if not hmac.compare_digest(expected_hash, secret_record.secret_hash):
        _handle_failed_attempt(secret_record)
        raise AuthenticationError("Invalid credentials")

    _reset_failed_attempts(secret_record)
    secret_record.last_used_at = now
    secret_record.status = "active"
    secret_record.save()

    if login_data.username and user.username != login_data.username:
        user.username = login_data.username
        user.save()

    access_token = create_access_token(user.telegram_user_id, user.username, login_data.client_id)
    refresh_token, session_id = create_refresh_token(user.telegram_user_id, login_data.client_id)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )

    logger.info(
        "secret_login_success",
        extra={
            "user_id": user.telegram_user_id,
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
    refresh_token_record = RefreshToken.get_or_none(RefreshToken.token_hash == token_hash)
    if refresh_token_record and refresh_token_record.is_revoked:
        raise TokenRevokedError()

    # Get user
    user = User.select().where(User.telegram_user_id == user_id).first()
    if not user:
        raise ResourceNotFoundError("User", user_id)

    # Generate new access token with same client_id
    access_token = create_access_token(user.telegram_user_id, user.username, client_id)

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
    admin_user = _require_owner(user)
    validate_client_id(payload.client_id)
    _ensure_user_allowed(payload.user_id)

    target_user = _get_target_user(payload.user_id, payload.username)

    _revoke_active_secrets(target_user, payload.client_id)
    secret_value, record = _build_secret_record(
        target_user,
        payload.client_id,
        provided_secret=payload.secret,
        label=payload.label,
        description=payload.description,
        expires_at=_coerce_naive(payload.expires_at),
    )

    logger.info(
        "secret_key_created",
        extra={
            "created_by": admin_user.telegram_user_id,
            "user_id": target_user.telegram_user_id,
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
    admin_user = _require_owner(user)

    record = ClientSecret.select().where(ClientSecret.id == key_id).first()
    if not record:
        raise ResourceNotFoundError("Secret key", key_id)

    _ensure_user_allowed(record.user_id)
    validate_client_id(record.client_id)

    new_secret_value = (
        _validate_secret_value(payload.secret, context="create")
        if payload.secret
        else _generate_secret_value()
    )
    record.secret_salt = secrets.token_hex(16)
    record.secret_hash = _hash_secret(new_secret_value, record.secret_salt)
    record.status = "active"
    record.failed_attempts = 0
    record.locked_until = None
    record.expires_at = _coerce_naive(payload.expires_at) or record.expires_at
    record.label = payload.label if payload.label is not None else record.label
    record.description = (
        payload.description if payload.description is not None else record.description
    )
    record.last_used_at = None
    record.save()

    logger.info(
        "secret_key_rotated",
        extra={
            "rotated_by": admin_user.telegram_user_id,
            "user_id": record.user_id,
            "client_id": record.client_id,
            "key_id": record.id,
        },
    )

    return success_response(
        SecretKeyCreateResponse(secret=new_secret_value, key=_serialize_secret(record))
    )


@router.post("/secret-keys/{key_id}/revoke")
async def revoke_secret_key(
    key_id: int, payload: SecretKeyRevokeRequest | None = None, user=Depends(get_current_user)
):
    """Revoke an existing client secret (owner-only)."""
    _ensure_secret_login_enabled()
    admin_user = _require_owner(user)

    record = ClientSecret.select().where(ClientSecret.id == key_id).first()
    if not record:
        raise ResourceNotFoundError("Secret key", key_id)

    _ensure_user_allowed(record.user_id)
    record.status = "revoked"
    record.failed_attempts = 0
    record.locked_until = None
    record.save()

    logger.info(
        "secret_key_revoked",
        extra={
            "revoked_by": admin_user.telegram_user_id,
            "user_id": record.user_id,
            "client_id": record.client_id,
            "key_id": record.id,
            "reason": payload.reason if payload else None,
        },
    )

    return success_response(SecretKeyActionResponse(key=_serialize_secret(record)))


@router.get("/secret-keys")
async def list_secret_keys(
    user=Depends(get_current_user),
    user_id: int | None = None,
    client_id: str | None = None,
    status: str | None = None,
):
    """List stored client secrets (owner-only)."""
    _ensure_secret_login_enabled()
    _require_owner(user)

    query = ClientSecret.select()

    if user_id is not None:
        _ensure_user_allowed(user_id)
        query = query.join(User).where(User.telegram_user_id == user_id)
    if client_id:
        query = query.where(ClientSecret.client_id == client_id)
    if status:
        query = query.where(ClientSecret.status == status)

    keys = [_serialize_secret(rec) for rec in query]
    return success_response(SecretKeyListResponse(keys=keys))


@router.get("/me")
async def get_current_user_info(user=Depends(get_current_user)):
    """Get current authenticated user information."""
    user_record = User.select().where(User.telegram_user_id == user["user_id"]).first()

    # Ensure user record exists (create if missing - edge case for legacy tokens)
    if not user_record:
        user_record = User.create(
            telegram_user_id=user["user_id"],
            username=user.get("username"),
            is_owner=False,
        )

    return success_response(
        UserInfo(
            user_id=user["user_id"],
            username=user.get("username") or "",
            client_id=user["client_id"],
            is_owner=user_record.is_owner,
            created_at=user_record.created_at.isoformat() + "Z",
        )
    )


@router.get("/me/telegram")
async def get_telegram_link_status(user=Depends(get_current_user)):
    """Fetch current Telegram link status."""
    user_record = _ensure_user(user["user_id"])
    return success_response(_link_status_payload(user_record))


@router.delete("/me")
async def delete_account(user=Depends(get_current_user)):
    """Delete the current user account and all associated data."""
    user_id = user["user_id"]
    user_record = _ensure_user(user_id)

    # Delete all associated data
    # Note: Use a transaction to ensure atomicity
    # Assuming CASCADE delete is set up in db models for related data
    try:
        user_record.delete_instance(recursive=True)
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

    user, created = User.get_or_create(
        telegram_user_id=apple_user_id,
        defaults={
            "username": display_name or email or f"apple_{apple_user_id}",
            "is_owner": False,
        },
    )

    if created:
        logger.info(
            f"Created new user via Apple login: {apple_user_id}",
            extra={"email": email, "apple_sub": apple_sub},
        )

    # Generate tokens
    access_token = create_access_token(user.telegram_user_id, user.username, login_data.client_id)
    refresh_token, session_id = create_refresh_token(user.telegram_user_id, login_data.client_id)

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

    user, created = User.get_or_create(
        telegram_user_id=google_user_id,
        defaults={
            "username": name or email or f"google_{google_user_id}",
            "is_owner": False,
        },
    )

    if created:
        logger.info(
            f"Created new user via Google login: {google_user_id}",
            extra={"email": email, "google_sub": google_sub},
        )

    # Generate tokens
    access_token = create_access_token(user.telegram_user_id, user.username, login_data.client_id)
    refresh_token, session_id = create_refresh_token(user.telegram_user_id, login_data.client_id)

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
    user_record = _ensure_user(user["user_id"])
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    nonce = secrets.token_urlsafe(32)
    _set_link_nonce(user_record, nonce, expires_at)
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
    user_record = _ensure_user(user["user_id"])

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

    user_record.linked_telegram_user_id = payload.telegram_user_id
    user_record.linked_telegram_username = payload.username
    user_record.linked_telegram_photo_url = payload.photo_url
    user_record.linked_telegram_first_name = payload.first_name
    user_record.linked_telegram_last_name = payload.last_name
    user_record.linked_at = now
    _clear_link_nonce(user_record)

    logger.info(
        "telegram_linked",
        extra={
            "user_id": user_record.telegram_user_id,
            "linked_telegram_user_id": payload.telegram_user_id,
            "username": payload.username,
        },
    )

    return success_response(_link_status_payload(user_record))


@router.delete("/me/telegram")
async def unlink_telegram(user=Depends(get_current_user)):
    """Unlink Telegram account."""
    user_record = _ensure_user(user["user_id"])
    user_record.linked_telegram_user_id = None
    user_record.linked_telegram_username = None
    user_record.linked_telegram_photo_url = None
    user_record.linked_telegram_first_name = None
    user_record.linked_telegram_last_name = None
    user_record.linked_at = None
    _clear_link_nonce(user_record)

    logger.info(
        "telegram_unlinked",
        extra={
            "user_id": user_record.telegram_user_id,
        },
    )

    return success_response(_link_status_payload(user_record))


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

        # Find token in DB
        refresh_token_record = RefreshToken.get_or_none(RefreshToken.token_hash == token_hash)

        if refresh_token_record:
            refresh_token_record.is_revoked = True
            refresh_token_record.save()
            logger.info("Revoked refresh token", extra={"token_id": refresh_token_record.id})

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

    sessions = (
        RefreshToken.select()
        .where(
            (RefreshToken.user == user_id)
            & (~RefreshToken.is_revoked)
            & (RefreshToken.expires_at > now)
        )
        .order_by(RefreshToken.last_used_at.desc())
    )

    formatted_sessions = []
    for s in sessions:
        last_used = s.last_used_at
        if last_used and hasattr(last_used, "isoformat"):
            last_used = last_used.isoformat() + "Z"
        elif last_used:
            # Already a string or something else
            last_used = str(last_used) + "Z"

        created = s.created_at
        if created and hasattr(created, "isoformat"):
            created = created.isoformat() + "Z"
        else:
            created = str(created) + "Z"

        formatted_sessions.append(
            SessionInfo(
                id=s.id,
                client_id=s.client_id,
                device_info=s.device_info,
                ip_address=s.ip_address,
                last_used_at=last_used,
                created_at=created,
            )
        )

    return success_response({"sessions": formatted_sessions})

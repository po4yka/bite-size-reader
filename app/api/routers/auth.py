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

from app.api.models.responses import (
    AuthTokensResponse,
    TokenPair,
    UserInfo,
    success_response,
)
from app.config import AppConfig, Config, load_config
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import ClientSecret, User

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


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


class SecretLoginRequest(BaseModel):
    """Request body for secret-key login."""

    model_config = ConfigDict(populate_by_name=True)

    user_id: int
    client_id: str = Field(..., min_length=1, max_length=100)
    secret: str
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
        raise HTTPException(
            status_code=401,
            detail=f"Authentication expired ({age_seconds} seconds old). Please log in again.",
        )

    if age_seconds < -60:  # Allow 1 minute clock skew
        logger.warning(
            f"Telegram auth timestamp in future for user {user_id}. Skew: {-age_seconds}s",
            extra={"user_id": user_id, "skew_seconds": -age_seconds},
        )
        raise HTTPException(
            status_code=401, detail="Authentication timestamp is in the future. Check device clock."
        )

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
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: BOT_TOKEN is not set.",
        ) from err

    if not bot_token:
        logger.error("BOT_TOKEN is empty - cannot verify Telegram auth")
        raise HTTPException(
            status_code=500,
            detail="Server misconfiguration: BOT_TOKEN is empty.",
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
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication hash. Please try logging in again.",
        )

    # Verify user is in whitelist
    allowed_ids = Config.get_allowed_user_ids()
    if user_id not in allowed_ids:
        logger.warning(
            f"User {user_id} not in whitelist",
            extra={"user_id": user_id, "username": username},
        )
        raise HTTPException(
            status_code=403,
            detail="User not authorized. Contact administrator to request access.",
        )

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


def create_refresh_token(user_id: int, client_id: str | None = None) -> str:
    """Create JWT refresh token."""
    return create_token(user_id, "refresh", client_id=client_id)


def validate_client_id(client_id: str | None) -> bool:
    """
    Validate client_id against allowlist.

    Args:
        client_id: Client application ID to validate

    Returns:
        True if valid

    Raises:
        HTTPException: If client_id is invalid or not allowed
    """
    if not client_id:
        raise HTTPException(
            status_code=401,
            detail="Client ID is required. Please update your app to the latest version.",
        )

    # Validate format
    if not all(c.isalnum() or c in "-_." for c in client_id):
        logger.warning(
            f"Invalid client ID format: {client_id}",
            extra={"client_id": client_id},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid client ID format.",
        )

    if len(client_id) > 100:
        logger.warning(
            f"Client ID too long: {client_id}",
            extra={"client_id": client_id, "length": len(client_id)},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid client ID format.",
        )

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
        raise HTTPException(
            status_code=403,
            detail="Client application not authorized. Please contact administrator.",
        )

    return True


def _ensure_secret_login_enabled() -> None:
    if not _get_auth_config().secret_login_enabled:
        raise HTTPException(status_code=404, detail="Secret-key login is disabled")


def _ensure_user_allowed(user_id: int) -> None:
    allowed_ids = Config.get_allowed_user_ids()
    if user_id not in allowed_ids:
        logger.warning(
            "User not authorized for secret login",
            extra={"user_id": user_id},
        )
        raise HTTPException(
            status_code=403,
            detail="User not authorized. Contact administrator to request access.",
        )


def _require_owner(user: dict) -> User:
    user_record = User.select().where(User.telegram_user_id == user["user_id"]).first()
    if not user_record or not user_record.is_owner:
        raise HTTPException(status_code=403, detail="Owner permissions required")
    return user_record


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
        msg = "Invalid secret length"
        status = 401 if context == "login" else 400
        raise HTTPException(status_code=status, detail=msg)
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
        raise HTTPException(status_code=401, detail="Secret has expired")


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


def decode_token(token: str) -> dict:
    """Decode and validate JWT token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as err:
        raise HTTPException(status_code=401, detail="Token has expired") from err
    except jwt.InvalidTokenError as err:
        raise HTTPException(status_code=401, detail="Invalid token") from err


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Dependency to get current authenticated user.

    Validates JWT token and returns user data.
    """
    token = credentials.credentials
    payload = decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Verify user is still in whitelist
    allowed_ids = Config.get_allowed_user_ids()
    if user_id not in allowed_ids:
        raise HTTPException(status_code=403, detail="User not authorized")

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
        refresh_token = create_refresh_token(user.telegram_user_id, login_data.client_id)

        logger.info(
            f"User {user.telegram_user_id} logged in successfully from client {login_data.client_id}",
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
        return success_response(AuthTokensResponse(tokens=tokens))

    except HTTPException:
        # Re-raise HTTP exceptions from verify_telegram_auth or validate_client_id
        raise
    except Exception as e:
        logger.error(f"Login failed for user {login_data.telegram_user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Authentication failed. Please try again."
        ) from e


@router.post("/secret-login")
async def secret_login(login_data: SecretLoginRequest):
    """Exchange a pre-registered client secret for JWT tokens."""
    _ensure_secret_login_enabled()
    validate_client_id(login_data.client_id)
    _ensure_user_allowed(login_data.user_id)
    now = _utcnow_naive()

    user = User.select().where(User.telegram_user_id == login_data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found for secret login")

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
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if secret_record.status == "revoked":
        raise HTTPException(status_code=401, detail="Secret has been revoked")

    if secret_record.status == "locked":
        if secret_record.locked_until and secret_record.locked_until < now:
            secret_record.status = "active"
            _reset_failed_attempts(secret_record)
        else:
            raise HTTPException(status_code=403, detail="Secret is temporarily locked")

    _check_expired(secret_record)

    provided_secret = _validate_secret_value(login_data.secret, context="login")
    expected_hash = _hash_secret(provided_secret, secret_record.secret_salt)

    if not hmac.compare_digest(expected_hash, secret_record.secret_hash):
        _handle_failed_attempt(secret_record)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    _reset_failed_attempts(secret_record)
    secret_record.last_used_at = now
    secret_record.status = "active"
    secret_record.save()

    if login_data.username and user.username != login_data.username:
        user.username = login_data.username
        user.save()

    access_token = create_access_token(user.telegram_user_id, user.username, login_data.client_id)
    refresh_token = create_refresh_token(user.telegram_user_id, login_data.client_id)

    tokens = TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        token_type="Bearer",
    )

    logger.info(
        "secret_login_success",
        extra={"user_id": user.telegram_user_id, "client_id": login_data.client_id},
    )

    return success_response(AuthTokensResponse(tokens=tokens))


@router.post("/refresh")
async def refresh_access_token(refresh_data: RefreshTokenRequest):
    """
    Refresh an expired access token using a refresh token.
    """
    payload = decode_token(refresh_data.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    # Validate client_id from refresh token
    client_id = payload.get("client_id")
    validate_client_id(client_id)

    # Get user
    user = User.select().where(User.telegram_user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate new access token with same client_id
    access_token = create_access_token(user.telegram_user_id, user.username, client_id)

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
        raise HTTPException(status_code=404, detail="Secret key not found")

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
        raise HTTPException(status_code=404, detail="Secret key not found")

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

    return success_response(
        UserInfo(
            user_id=user["user_id"],
            username=user.get("username"),
            client_id=user.get("client_id"),
            is_owner=user_record.is_owner if user_record else False,
            created_at=user_record.created_at.isoformat() + "Z" if user_record else None,
        )
    )

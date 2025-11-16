"""
Authentication endpoints and utilities.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timedelta, UTC
import jwt
import hashlib
import hmac
import time

from app.config import Config
from app.db.models import User
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()
security = HTTPBearer()

# JWT configuration
SECRET_KEY = Config.get("JWT_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "your-secret-key-change-in-production":
    raise RuntimeError(
        "JWT_SECRET_KEY environment variable must be set to a secure random value. "
        "Generate one with: openssl rand -hex 32"
    )

if len(SECRET_KEY) < 32:
    raise RuntimeError(
        f"JWT_SECRET_KEY must be at least 32 characters long. Current length: {len(SECRET_KEY)}"
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30

logger.info("JWT authentication initialized with secure secret")


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
    bot_token = Config.get("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN not configured - cannot verify Telegram auth")
        raise RuntimeError("BOT_TOKEN not configured")

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

        return {
            "success": True,
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "token_type": "Bearer",
            },
        }

    except HTTPException:
        # Re-raise HTTP exceptions from verify_telegram_auth or validate_client_id
        raise
    except Exception as e:
        logger.error(f"Login failed for user {login_data.telegram_user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Authentication failed. Please try again."
        ) from e


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

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        },
    }


@router.get("/me")
async def get_current_user_info(user=Depends(get_current_user)):
    """Get current authenticated user information."""
    user_record = User.select().where(User.telegram_user_id == user["user_id"]).first()

    return {
        "success": True,
        "data": {
            "user_id": user["user_id"],
            "username": user.get("username"),
            "client_id": user.get("client_id"),
            "is_owner": user_record.is_owner if user_record else False,
            "created_at": user_record.created_at.isoformat() + "Z" if user_record else None,
        },
    }

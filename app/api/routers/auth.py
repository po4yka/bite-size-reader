"""
Authentication endpoints and utilities.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from datetime import datetime, timedelta
import jwt
import hashlib
import hmac

from app.config import Config
from app.db.models import User
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()
security = HTTPBearer()

# JWT configuration
SECRET_KEY = Config.get("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30


class TelegramLoginRequest(BaseModel):
    """Request body for Telegram login."""

    telegram_user_id: int
    auth_hash: str
    timestamp: int
    username: str = None


class RefreshTokenRequest(BaseModel):
    """Request body for token refresh."""

    refresh_token: str


def verify_telegram_auth(user_id: int, auth_hash: str, timestamp: int) -> bool:
    """
    Verify Telegram authentication hash.

    In production, this should verify against Telegram's auth data:
    https://core.telegram.org/widgets/login#checking-authorization
    """
    # TODO: Implement proper Telegram auth verification
    # For now, just check if user is in whitelist

    allowed_ids = Config.get_allowed_user_ids()
    return user_id in allowed_ids


def create_access_token(user_id: int, username: str = None) -> str:
    """Create JWT access token."""
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(user_id: int) -> str:
    """Create JWT refresh token."""
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "user_id": user_id,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


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

    return {
        "user_id": user_id,
        "username": payload.get("username"),
    }


@router.post("/telegram-login")
async def telegram_login(login_data: TelegramLoginRequest):
    """
    Exchange Telegram authentication data for JWT tokens.

    Verifies Telegram auth hash and returns access + refresh tokens.
    """
    # Verify Telegram auth
    if not verify_telegram_auth(
        login_data.telegram_user_id,
        login_data.auth_hash,
        login_data.timestamp,
    ):
        raise HTTPException(status_code=403, detail="Invalid Telegram authentication")

    # Get or create user
    user, created = User.get_or_create(
        telegram_user_id=login_data.telegram_user_id,
        defaults={"username": login_data.username, "is_owner": True},
    )

    if not created and login_data.username and user.username != login_data.username:
        user.username = login_data.username
        user.save()

    # Generate tokens
    access_token = create_access_token(user.telegram_user_id, user.username)
    refresh_token = create_refresh_token(user.telegram_user_id)

    logger.info(f"User {user.telegram_user_id} logged in successfully")

    return {
        "success": True,
        "data": {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "token_type": "Bearer",
        },
    }


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

    # Get user
    user = User.select().where(User.telegram_user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate new access token
    access_token = create_access_token(user.telegram_user_id, user.username)

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
            "is_owner": user_record.is_owner if user_record else False,
            "created_at": user_record.created_at.isoformat() + "Z" if user_record else None,
        },
    }

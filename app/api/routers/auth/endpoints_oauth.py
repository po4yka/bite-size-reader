"""
OAuth login endpoints (Apple / Google).
"""

from __future__ import annotations

from typing import Any

from app.api.dependencies.database import get_user_repository
from app.api.exceptions import AuthenticationError, AuthorizationError
from app.api.models.auth import AppleLoginRequest, GoogleLoginRequest  # noqa: TC001
from app.api.models.responses import (
    LoginData,
    PreferencesData,
    TokenPair,
    UserInfo,
    success_response,
)
from app.api.routers.auth._fastapi import APIRouter
from app.api.routers.auth.oauth import (
    derive_user_id_from_sub,
    verify_apple_id_token,
    verify_google_id_token,
)
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    validate_client_id,
)
from app.api.search_helpers import isotime
from app.config import Config
from app.core.logging_utils import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _build_preferences(user_record: dict[str, Any]) -> PreferencesData:
    """Build preferences payload from a user record, matching user.py logic."""
    default_preferences: dict[str, Any] = {
        "lang_preference": "en",
        "notification_settings": {"enabled": True, "frequency": "daily"},
        "app_settings": {"theme": "dark", "font_size": "medium"},
    }
    preferences: dict[str, Any] = {
        "lang_preference": default_preferences["lang_preference"],
        "notification_settings": {**default_preferences["notification_settings"]},
        "app_settings": {**default_preferences["app_settings"]},
    }
    stored_preferences = user_record.get("preferences_json")
    if isinstance(stored_preferences, dict):
        lang_preference = stored_preferences.get("lang_preference")
        if isinstance(lang_preference, str) and lang_preference:
            preferences["lang_preference"] = lang_preference
        notification_settings = stored_preferences.get("notification_settings")
        if isinstance(notification_settings, dict):
            preferences["notification_settings"].update(notification_settings)
        app_settings = stored_preferences.get("app_settings")
        if isinstance(app_settings, dict):
            preferences["app_settings"].update(app_settings)
    return PreferencesData(
        user_id=user_record.get("telegram_user_id", 0),
        telegram_username=user_record.get("username"),
        lang_preference=preferences.get("lang_preference"),
        notification_settings=preferences.get("notification_settings"),
        app_settings=preferences.get("app_settings"),
    )


def _ensure_allowed_user_id(user_id: int, *, provider: str, sub: str) -> None:
    allowed_ids = Config.get_allowed_user_ids()
    if allowed_ids and user_id not in allowed_ids:
        logger.warning(
            "oauth_user_not_authorized",
            extra={"user_id": user_id, "provider": provider, "sub": sub},
        )
        raise AuthorizationError("User not authorized. Contact administrator to request access.")


@router.post("/apple-login")
async def apple_login(login_data: AppleLoginRequest):
    """Exchange Apple authentication data for JWT tokens."""
    logger.info("apple_login_attempt", extra={"client_id": login_data.client_id})
    validate_client_id(login_data.client_id)

    claims = verify_apple_id_token(login_data.id_token, login_data.client_id)
    apple_sub = claims.get("sub")
    if not apple_sub:
        raise AuthenticationError("Apple ID token missing 'sub' claim")

    apple_user_id = derive_user_id_from_sub("apple", apple_sub)
    _ensure_allowed_user_id(apple_user_id, provider="apple", sub=apple_sub)

    display_name = None
    if login_data.given_name or login_data.family_name:
        name_parts = [login_data.given_name, login_data.family_name]
        display_name = " ".join(p for p in name_parts if p)
    email = claims.get("email")

    user_repo = get_user_repository()
    user, created = await user_repo.async_get_or_create_user(
        apple_user_id,
        username=display_name or email or f"apple_{apple_user_id}",
        is_owner=False,
    )
    if created:
        logger.info(
            "oauth_user_created",
            extra={"provider": "apple", "user_id": apple_user_id, "email": email, "sub": apple_sub},
        )

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
    user_info = UserInfo(
        user_id=user_id,
        username=username or "",
        client_id=login_data.client_id,
        is_owner=user.get("is_owner", False),
        created_at=isotime(user.get("created_at", "")),
    )
    preferences = _build_preferences(user)
    return success_response(
        LoginData(
            tokens=tokens,
            user=user_info,
            preferences=preferences,
            session_id=session_id,
        )
    )


@router.post("/google-login")
async def google_login(login_data: GoogleLoginRequest):
    """Exchange Google authentication data for JWT tokens."""
    logger.info("google_login_attempt", extra={"client_id": login_data.client_id})
    validate_client_id(login_data.client_id)

    claims = verify_google_id_token(login_data.id_token, login_data.client_id)
    google_sub = claims.get("sub")
    if not google_sub:
        raise AuthenticationError("Google ID token missing 'sub' claim")

    google_user_id = derive_user_id_from_sub("google", google_sub)
    _ensure_allowed_user_id(google_user_id, provider="google", sub=google_sub)

    email = claims.get("email")
    name = claims.get("name")

    user_repo = get_user_repository()
    user, created = await user_repo.async_get_or_create_user(
        google_user_id,
        username=name or email or f"google_{google_user_id}",
        is_owner=False,
    )
    if created:
        logger.info(
            "oauth_user_created",
            extra={
                "provider": "google",
                "user_id": google_user_id,
                "email": email,
                "sub": google_sub,
            },
        )

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
    user_info = UserInfo(
        user_id=user_id,
        username=username or "",
        client_id=login_data.client_id,
        is_owner=user.get("is_owner", False),
        created_at=isotime(user.get("created_at", "")),
    )
    preferences = _build_preferences(user)
    return success_response(
        LoginData(
            tokens=tokens,
            user=user_info,
            preferences=preferences,
            session_id=session_id,
        )
    )

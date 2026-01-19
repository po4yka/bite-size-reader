"""
Authentication router package.

This package provides authentication endpoints and utilities for the API.
All public exports are re-exported here for backward compatibility.
"""

# Security dependencies (critical - imported by 7+ routers)
from app.api.routers.auth.dependencies import get_current_user, security

# Router for endpoint registration
from app.api.routers.auth.endpoints import router

# OAuth verification
from app.api.routers.auth.oauth import (
    derive_user_id_from_sub,
    verify_apple_id_token,
    verify_google_id_token,
)

# Secret auth utilities (for advanced use cases)
from app.api.routers.auth.secret_auth import (
    coerce_naive,
    ensure_secret_login_enabled,
    ensure_user_allowed,
    generate_secret_value,
    hash_secret,
    serialize_secret,
    utcnow_naive,
    validate_secret_value,
)

# Telegram verification
from app.api.routers.auth.telegram import verify_telegram_auth

# Token functions
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    validate_client_id,
)

__all__ = [
    "ACCESS_TOKEN_EXPIRE_MINUTES",
    "ALGORITHM",
    "REFRESH_TOKEN_EXPIRE_DAYS",
    "SECRET_KEY",
    "coerce_naive",
    "create_access_token",
    "create_refresh_token",
    "create_token",
    "decode_token",
    "derive_user_id_from_sub",
    "ensure_secret_login_enabled",
    "ensure_user_allowed",
    "generate_secret_value",
    "get_current_user",
    "hash_secret",
    "router",
    "security",
    "serialize_secret",
    "utcnow_naive",
    "validate_client_id",
    "validate_secret_value",
    "verify_apple_id_token",
    "verify_google_id_token",
    "verify_telegram_auth",
]

"""Telegram Mini App (WebApp) initData validation.

Implements HMAC-SHA256 validation per:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qs

from app.api.exceptions import AuthenticationError, AuthorizationError
from app.config import Config

logger = logging.getLogger(__name__)

# initData is valid for 15 minutes, with 1 minute clock skew tolerance
_AUTH_DATE_MAX_AGE_SEC = 15 * 60
_CLOCK_SKEW_SEC = 60


def verify_telegram_webapp_init_data(init_data: str) -> dict:
    """Validate Telegram WebApp initData and return parsed user info.

    Args:
        init_data: The raw initData query string from Telegram.WebApp.initData.

    Returns:
        Dict with user info: {"user_id": int, "username": str | None, ...}

    Raises:
        AuthenticationError: If validation fails.
        AuthorizationError: If user is not in ALLOWED_USER_IDS.
    """
    if not init_data or not init_data.strip():
        raise AuthenticationError("Empty initData")

    bot_token = Config.get("BOT_TOKEN", "")
    if not bot_token:
        raise AuthenticationError("Bot token not configured")

    # Parse query string
    parsed = parse_qs(init_data, keep_blank_values=True)

    # Extract hash
    received_hash = parsed.pop("hash", [None])[0]
    if not received_hash:
        raise AuthenticationError("Missing hash in initData")

    # Build data-check-string: sorted key=value pairs, newline-joined
    # Each value is the first element from parse_qs (since keep_blank_values=True)
    data_check_pairs = sorted(f"{key}={values[0]}" for key, values in parsed.items() if values)
    data_check_string = "\n".join(data_check_pairs)

    # Secret = HMAC-SHA256("WebAppData", BOT_TOKEN)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()

    # Computed hash = HMAC-SHA256(secret, data_check_string)
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(computed_hash, received_hash):
        raise AuthenticationError("Invalid initData signature")

    # Check auth_date freshness
    auth_date_str = parsed.get("auth_date", [None])[0]
    if not auth_date_str:
        raise AuthenticationError("Missing auth_date in initData")

    try:
        auth_date = int(auth_date_str)
    except (ValueError, TypeError) as exc:
        raise AuthenticationError("Invalid auth_date format") from exc

    now = int(time.time())
    age = now - auth_date
    if age > _AUTH_DATE_MAX_AGE_SEC + _CLOCK_SKEW_SEC:
        raise AuthenticationError("initData has expired")
    if age < -_CLOCK_SKEW_SEC:
        raise AuthenticationError("initData auth_date is in the future")

    # Parse user JSON
    user_json_str = parsed.get("user", [None])[0]
    if not user_json_str:
        raise AuthenticationError("Missing user in initData")

    try:
        user_data = json.loads(user_json_str)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AuthenticationError("Invalid user JSON in initData") from exc

    user_id = user_data.get("id")
    if not user_id:
        raise AuthenticationError("Missing user id in initData")

    # Verify user is in whitelist (fail closed when not configured)
    allowed_ids = Config.get_allowed_user_ids()
    if not allowed_ids:
        raise AuthorizationError("No authorized users configured")
    if user_id not in allowed_ids:
        raise AuthorizationError("User not authorized")

    return {
        "user_id": user_id,
        "username": user_data.get("username"),
        "first_name": user_data.get("first_name"),
        "last_name": user_data.get("last_name"),
    }

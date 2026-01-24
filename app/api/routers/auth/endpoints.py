"""
Authentication API endpoints.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Any

try:
    from fastapi import APIRouter, Depends
except Exception:  # pragma: no cover - fallback for environments without compatible FastAPI
    APIRouter: Any = type("APIRouter", (), {})  # type: ignore

    def Depends(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc, unused-ignore]  # noqa: N802
        return None


from app.api.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from app.api.models.auth import (
    AppleLoginRequest,
    GoogleLoginRequest,
    RefreshTokenRequest,
    SecretKeyActionResponse,
    SecretKeyCreateRequest,
    SecretKeyCreateResponse,
    SecretKeyListResponse,
    SecretKeyRevokeRequest,
    SecretKeyRotateRequest,
    SecretLoginRequest,
    SessionInfo,
    TelegramLinkBeginResponse,
    TelegramLinkCompleteRequest,
    TelegramLoginRequest,
)
from app.api.models.responses import (
    AuthTokensResponse,
    TokenPair,
    UserInfo,
    success_response,
)
from app.api.routers.auth.dependencies import get_current_user
from app.api.routers.auth.oauth import (
    derive_user_id_from_sub,
    verify_apple_id_token,
    verify_google_id_token,
)
from app.api.routers.auth.secret_auth import (
    build_secret_record,
    check_expired,
    coerce_naive,
    ensure_secret_login_enabled,
    ensure_user_allowed,
    generate_secret_value,
    handle_failed_attempt,
    hash_secret,
    reset_failed_attempts,
    revoke_active_secrets,
    serialize_secret,
    utcnow_naive,
    validate_secret_value,
)
from app.api.routers.auth.telegram import verify_telegram_auth
from app.api.routers.auth.tokens import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_client_id,
)
from app.api.services.auth_service import AuthService
from app.config import Config
from app.core.logging_utils import get_logger, log_exception
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


@router.post("/telegram-login")
async def telegram_login(login_data: TelegramLoginRequest):
    """
    Exchange Telegram authentication data for JWT tokens.

    Verifies Telegram auth hash using HMAC-SHA256 and returns access + refresh tokens.
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
        raise
    except Exception as e:
        logger.error(f"Login failed for user {login_data.telegram_user_id}: {e}", exc_info=True)
        raise ProcessingError("Authentication failed. Please try again.") from e


@router.post("/secret-login")
async def secret_login(login_data: SecretLoginRequest):
    """Exchange a pre-registered client secret for JWT tokens."""
    ensure_secret_login_enabled()
    validate_client_id(login_data.client_id)
    ensure_user_allowed(login_data.user_id)
    now = utcnow_naive()

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
                await reset_failed_attempts(secret_record)
            else:
                raise AuthorizationError("Secret is temporarily locked")
        else:
            raise AuthorizationError("Secret is temporarily locked")

    await check_expired(secret_record)

    provided_secret = validate_secret_value(login_data.secret, context="login")
    expected_hash = hash_secret(provided_secret, secret_record.get("secret_salt", ""))

    if not hmac.compare_digest(expected_hash, secret_record.get("secret_hash", "")):
        await handle_failed_attempt(secret_record)
        raise AuthenticationError("Invalid credentials")

    await reset_failed_attempts(secret_record)
    await auth_repo.async_update_client_secret(
        secret_record["id"],
        last_used_at=now,
        status="active",
    )

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
    """Refresh an expired access token using a refresh token."""
    from app.api.exceptions import TokenInvalidError, TokenRevokedError

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
    ensure_secret_login_enabled()
    admin_user = await AuthService.require_owner(user)
    validate_client_id(payload.client_id)
    ensure_user_allowed(payload.user_id)

    target_user = await AuthService.get_target_user(payload.user_id, payload.username)
    target_user_id = target_user.get("telegram_user_id", payload.user_id)

    await revoke_active_secrets(target_user_id, payload.client_id)
    secret_value, record = await build_secret_record(
        target_user_id,
        payload.client_id,
        provided_secret=payload.secret,
        label=payload.label,
        description=payload.description,
        expires_at=coerce_naive(payload.expires_at),
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
        SecretKeyCreateResponse(secret=secret_value, key=serialize_secret(record))
    )


@router.post("/secret-keys/{key_id}/rotate")
async def rotate_secret_key(
    key_id: int, payload: SecretKeyRotateRequest, user=Depends(get_current_user)
):
    """Rotate an existing client secret (owner-only)."""
    ensure_secret_login_enabled()
    admin_user = await AuthService.require_owner(user)

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

    ensure_user_allowed(record_user_id)
    validate_client_id(record.get("client_id", ""))

    new_secret_value = (
        validate_secret_value(payload.secret, context="create")
        if payload.secret
        else generate_secret_value()
    )
    new_salt = secrets.token_hex(16)
    new_hash = hash_secret(new_secret_value, new_salt)

    await auth_repo.async_update_client_secret(
        key_id,
        secret_salt=new_salt,
        secret_hash=new_hash,
        status="active",
        failed_attempts=0,
        locked_until=None,
        expires_at=coerce_naive(payload.expires_at) or record.get("expires_at"),
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
        SecretKeyCreateResponse(secret=new_secret_value, key=serialize_secret(updated_record or {}))
    )


@router.post("/secret-keys/{key_id}/revoke")
async def revoke_secret_key(
    key_id: int, payload: SecretKeyRevokeRequest | None = None, user=Depends(get_current_user)
):
    """Revoke an existing client secret (owner-only)."""
    ensure_secret_login_enabled()
    admin_user = await AuthService.require_owner(user)

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

    ensure_user_allowed(record_user_id)

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

    return success_response(SecretKeyActionResponse(key=serialize_secret(updated_record or {})))


@router.get("/secret-keys")
async def list_secret_keys(
    user=Depends(get_current_user),
    user_id: int | None = None,
    client_id: str | None = None,
    status: str | None = None,
):
    """List stored client secrets (owner-only)."""
    ensure_secret_login_enabled()
    await AuthService.require_owner(user)

    if user_id is not None:
        ensure_user_allowed(user_id)

    auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
    records = await auth_repo.async_list_client_secrets(
        user_id=user_id,
        client_id=client_id,
        status=status,
    )

    keys = [serialize_secret(rec) for rec in records]
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
    user_record = await AuthService.ensure_user(user["user_id"])
    return success_response(AuthService.build_link_status_payload(user_record))


@router.delete("/me")
async def delete_account(user=Depends(get_current_user)):
    """Delete the current user account and all associated data."""
    user_id = user["user_id"]
    # Verify user exists
    await AuthService.ensure_user(user_id)

    try:
        await AuthService.delete_user(user_id)
        logger.info(f"User {user_id} deleted their account")
        return success_response({"success": True})
    except Exception as e:
        logger.error(f"Failed to delete user {user_id}: {e}", exc_info=True)
        raise ProcessingError("Failed to delete account") from e


@router.post("/apple-login")
async def apple_login(login_data: AppleLoginRequest):
    """Exchange Apple authentication data for JWT tokens."""
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
    apple_user_id = derive_user_id_from_sub("apple", apple_sub)

    # Verify user is in whitelist (optional - can be removed for open registration)
    allowed_ids = Config.get_allowed_user_ids()
    if allowed_ids and apple_user_id not in allowed_ids:
        logger.warning(
            "User not authorized via Apple login",
            extra={"user_id": apple_user_id, "apple_sub": apple_sub},
        )
        raise AuthorizationError("User not authorized. Contact administrator to request access.")

    # Get or create user
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
    """Exchange Google authentication data for JWT tokens."""
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
    google_user_id = derive_user_id_from_sub("google", google_sub)

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
    name = claims.get("name")

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
    await AuthService.ensure_user(user["user_id"])
    expires_at = datetime.now(UTC) + timedelta(minutes=15)
    nonce = secrets.token_urlsafe(32)
    await AuthService.set_link_nonce(user["user_id"], nonce, expires_at)
    return success_response(
        TelegramLinkBeginResponse(
            nonce=nonce, expires_at=AuthService.format_datetime(expires_at) or ""
        )
    )


@router.post("/me/telegram/complete")
async def complete_telegram_link(
    payload: TelegramLinkCompleteRequest, user=Depends(get_current_user)
):
    """Complete Telegram linking by validating nonce and Telegram login payload."""
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

    now = utcnow_naive()
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

    await AuthService.complete_telegram_link(
        user_id,
        payload.telegram_user_id,
        payload.username,
        payload.photo_url,
        payload.first_name,
        payload.last_name,
    )

    # Re-fetch for response
    updated_user = await AuthService.ensure_user(user_id)

    logger.info(
        "telegram_linked",
        extra={
            "user_id": user_id,
            "linked_telegram_user_id": payload.telegram_user_id,
            "username": payload.username,
        },
    )

    return success_response(AuthService.build_link_status_payload(updated_user))


@router.delete("/me/telegram")
async def unlink_telegram(user=Depends(get_current_user)):
    """Unlink Telegram account."""
    user_id = user["user_id"]
    await AuthService.unlink_telegram(user_id)

    # Re-fetch for response
    updated_user = await AuthService.ensure_user(user_id)

    logger.info(
        "telegram_unlinked",
        extra={
            "user_id": user_id,
        },
    )

    return success_response(AuthService.build_link_status_payload(updated_user))


@router.post("/logout")
async def logout(
    request: RefreshTokenRequest,
    _: dict = Depends(get_current_user),
):
    """Logout by revoking the specific refresh token."""
    token = request.refresh_token
    try:
        token_hash = hashlib.sha256(token.encode()).hexdigest()

        auth_repo = SqliteAuthRepositoryAdapter(database_proxy)
        revoked = await auth_repo.async_revoke_refresh_token(token_hash)

        if revoked:
            logger.info("Revoked refresh token", extra={"token_hash": token_hash[:8] + "..."})

    except Exception as e:
        log_exception(logger, "logout_failed", e, level="warning")

    return success_response({"message": "Logged out successfully"})


@router.get("/sessions")
async def list_sessions(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """List active sessions for the current user."""
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

"""
Authentication service - business logic for auth operations.
"""

import asyncio
from datetime import datetime

from app.api.exceptions import AuthorizationError, ResourceNotFoundError
from app.api.models.auth import TelegramLinkStatus
from app.core.logging_utils import get_logger
from app.core.time_utils import UTC
from app.db.models import database_proxy
from app.infrastructure.persistence.sqlite.repositories.user_repository import (
    SqliteUserRepositoryAdapter,
)

logger = get_logger(__name__)


def _format_dt(dt_value: datetime | None) -> str | None:
    """Format datetime to ISO 8601 string with Z suffix."""
    if dt_value is None:
        return None
    if dt_value.tzinfo:
        return dt_value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return dt_value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _coerce_naive(dt_value: datetime | None) -> datetime | None:
    """Convert timezone-aware datetime to naive (UTC assumed)."""
    if dt_value is None:
        return None
    if dt_value.tzinfo:
        return dt_value.replace(tzinfo=None)
    return dt_value


def _utcnow_naive() -> datetime:
    """Get current UTC time as naive datetime."""
    return datetime.now(UTC).replace(tzinfo=None)


class AuthService:
    """Service for authentication-related business logic."""

    @staticmethod
    async def require_owner(user: dict) -> dict:
        """Verify user is an owner and return user data dict.

        Args:
            user: Current user dict from get_current_user dependency

        Returns:
            User record dict if owner

        Raises:
            AuthorizationError: If user is not an owner
        """
        user_repo = SqliteUserRepositoryAdapter(database_proxy)
        user_record = await user_repo.async_get_user_by_telegram_id(user["user_id"])
        if not user_record or not user_record.get("is_owner"):
            raise AuthorizationError("Owner permissions required")
        return user_record

    @staticmethod
    async def get_target_user(user_id: int, username: str | None = None) -> dict:
        """Get or create target user, returning user data dict.

        Args:
            user_id: Telegram user ID
            username: Optional username

        Returns:
            User data dict
        """
        user_repo = SqliteUserRepositoryAdapter(database_proxy)
        user_data, _ = await user_repo.async_get_or_create_user(
            user_id,
            username=username,
            is_owner=True,
        )
        return user_data

    @staticmethod
    async def ensure_user(user_id: int) -> dict:
        """Ensure user exists and return user data dict.

        Args:
            user_id: Telegram user ID

        Returns:
            User data dict

        Raises:
            ResourceNotFoundError: If user not found
        """
        user_repo = SqliteUserRepositoryAdapter(database_proxy)
        user = await user_repo.async_get_user_by_telegram_id(user_id)
        if not user:
            raise ResourceNotFoundError("User", user_id)
        return user

    @staticmethod
    async def set_link_nonce(user_id: int, nonce: str, expires_at: datetime) -> None:
        """Set link nonce for a user.

        TODO: Implement via repository. Currently uses direct model access.

        Args:
            user_id: Telegram user ID
            nonce: Link nonce value
            expires_at: Nonce expiration time
        """
        from app.db.models import User as UserModel

        def _set() -> None:
            user = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
            if user:
                user.link_nonce = nonce
                user.link_nonce_expires_at = _coerce_naive(expires_at)
                user.save()

        await asyncio.to_thread(_set)

    @staticmethod
    async def clear_link_nonce(user_id: int) -> None:
        """Clear link nonce for a user.

        TODO: Implement via repository. Currently uses direct model access.

        Args:
            user_id: Telegram user ID
        """
        from app.db.models import User as UserModel

        def _clear() -> None:
            user = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
            if user:
                user.link_nonce = None
                user.link_nonce_expires_at = None
                user.save()

        await asyncio.to_thread(_clear)

    @staticmethod
    def build_link_status_payload(user: dict) -> TelegramLinkStatus:
        """Build link status payload from user dict.

        Args:
            user: User data dict

        Returns:
            TelegramLinkStatus model
        """
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

    @staticmethod
    def format_datetime(dt_value: datetime | None) -> str | None:
        """Format datetime to ISO 8601 string with Z suffix.

        Args:
            dt_value: Datetime to format

        Returns:
            ISO 8601 formatted string or None
        """
        return _format_dt(dt_value)

    @staticmethod
    async def complete_telegram_link(
        user_id: int,
        telegram_user_id: int,
        username: str | None,
        photo_url: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> None:
        """Complete Telegram account linking.

        TODO: Implement via repository. Currently uses direct model access.

        Args:
            user_id: Main user ID
            telegram_user_id: Linked Telegram user ID
            username: Telegram username
            photo_url: Telegram photo URL
            first_name: First name
            last_name: Last name
        """
        from app.db.models import User as UserModel

        now = _utcnow_naive()

        def _update_link() -> None:
            user_rec = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
            if user_rec:
                user_rec.linked_telegram_user_id = telegram_user_id
                user_rec.linked_telegram_username = username
                user_rec.linked_telegram_photo_url = photo_url
                user_rec.linked_telegram_first_name = first_name
                user_rec.linked_telegram_last_name = last_name
                user_rec.linked_at = now
                user_rec.link_nonce = None
                user_rec.link_nonce_expires_at = None
                user_rec.save()

        await asyncio.to_thread(_update_link)

    @staticmethod
    async def unlink_telegram(user_id: int) -> None:
        """Unlink Telegram account.

        TODO: Implement via repository. Currently uses direct model access.

        Args:
            user_id: User ID to unlink
        """
        from app.db.models import User as UserModel

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

    @staticmethod
    async def delete_user(user_id: int) -> None:
        """Delete a user account and all associated data.

        TODO: Implement via repository with proper cascade delete.

        Args:
            user_id: User ID to delete
        """
        from app.db.models import User as UserModel

        def _delete() -> None:
            user_record = UserModel.get_or_none(UserModel.telegram_user_id == user_id)
            if user_record:
                user_record.delete_instance(recursive=True)

        await asyncio.to_thread(_delete)

"""SQLite implementation of user repository.

This adapter translates between domain User/Chat models and database records.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import peewee

from app.core.time_utils import UTC
from app.db.models import Chat, User, UserInteraction, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

if TYPE_CHECKING:
    from collections.abc import Mapping


class SqliteUserRepositoryAdapter(SqliteBaseRepository):
    """Adapter for user and interaction operations."""

    async def async_get_user_by_telegram_id(self, telegram_user_id: int) -> dict[str, Any] | None:
        """Get a user by Telegram user ID."""

        def _get() -> dict[str, Any] | None:
            user = User.get_or_none(User.telegram_user_id == telegram_user_id)
            return model_to_dict(user)

        return await self._execute(_get, operation_name="get_user_by_telegram_id", read_only=True)

    async def async_get_or_create_user(
        self,
        telegram_user_id: int,
        *,
        username: str | None = None,
        is_owner: bool = False,
    ) -> tuple[dict[str, Any], bool]:
        """Get or create a user by Telegram ID.

        Returns:
            Tuple of (user_data dict, created bool).
        """

        def _get_or_create() -> tuple[dict[str, Any], bool]:
            user, created = User.get_or_create(
                telegram_user_id=telegram_user_id,
                defaults={"username": username, "is_owner": is_owner},
            )
            return model_to_dict(user) or {}, created

        return await self._execute(_get_or_create, operation_name="get_or_create_user")

    async def async_update_user_preferences(
        self, telegram_user_id: int, preferences: dict[str, Any]
    ) -> None:
        """Update user preferences."""

        def _update() -> None:
            User.update(preferences_json=preferences).where(
                User.telegram_user_id == telegram_user_id
            ).execute()

        await self._execute(_update, operation_name="update_user_preferences")

    async def async_upsert_user(
        self, *, telegram_user_id: int, username: str | None = None, is_owner: bool = False
    ) -> None:
        """Upsert a user record."""

        def _upsert() -> None:
            User.insert(
                telegram_user_id=telegram_user_id,
                username=username,
                is_owner=is_owner,
            ).on_conflict(
                conflict_target=[User.telegram_user_id],
                update={"username": username, "is_owner": is_owner},
            ).execute()

        await self._execute(_upsert, operation_name="upsert_user")

    async def async_upsert_chat(
        self,
        *,
        chat_id: int,
        type_: str,
        title: str | None = None,
        username: str | None = None,
    ) -> None:
        """Upsert a chat record."""

        def _upsert() -> None:
            Chat.insert(
                chat_id=chat_id,
                type=type_,
                title=title,
                username=username,
            ).on_conflict(
                conflict_target=[Chat.chat_id],
                update={
                    "type": type_,
                    "title": title,
                    "username": username,
                },
            ).execute()

        await self._execute(_upsert, operation_name="upsert_chat")

    async def async_insert_user_interaction(
        self,
        *,
        user_id: int,
        interaction_type: str,
        chat_id: int | None = None,
        message_id: int | None = None,
        command: str | None = None,
        input_text: str | None = None,
        input_url: str | None = None,
        has_forward: bool = False,
        forward_from_chat_id: int | None = None,
        forward_from_chat_title: str | None = None,
        forward_from_message_id: int | None = None,
        media_type: str | None = None,
        correlation_id: str | None = None,
        structured_output_enabled: bool = False,
    ) -> int:
        """Insert a user interaction record."""

        def _insert() -> int:
            created = UserInteraction.create(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                interaction_type=interaction_type,
                command=command,
                input_text=input_text,
                input_url=input_url,
                has_forward=has_forward,
                forward_from_chat_id=forward_from_chat_id,
                forward_from_chat_title=forward_from_chat_title,
                forward_from_message_id=forward_from_message_id,
                media_type=media_type,
                correlation_id=correlation_id,
                structured_output_enabled=structured_output_enabled,
            )
            return created.id

        return await self._execute(_insert, operation_name="insert_user_interaction")

    async def async_update_user_interaction(
        self,
        interaction_id: int,
        *,
        updates: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> None:
        """Update a user interaction record."""

        def _update() -> None:
            update_values: dict[Any, Any] = {}

            # Merge updates dict and kwargs
            all_updates = dict(updates) if updates else {}
            all_updates.update(fields)

            if not all_updates:
                return

            # Map string keys to Peewee fields
            for key, value in all_updates.items():
                if hasattr(UserInteraction, key):
                    field_obj = getattr(UserInteraction, key)
                    if isinstance(field_obj, peewee.Field):
                        update_values[field_obj] = value

            if not update_values:
                return

            if hasattr(UserInteraction, "updated_at"):
                update_values[UserInteraction.updated_at] = dt.datetime.now(UTC)

            UserInteraction.update(update_values).where(
                UserInteraction.id == interaction_id
            ).execute()

        await self._execute(_update, operation_name="update_user_interaction")

    async def async_get_user_interactions(
        self,
        *,
        uid: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent user interactions."""

        def _get() -> list[dict[str, Any]]:
            interactions = (
                UserInteraction.select()
                .where(UserInteraction.user_id == uid)
                .order_by(UserInteraction.created_at.desc())
                .limit(limit)
            )
            return [model_to_dict(i) or {} for i in interactions]

        return await self._execute(_get, operation_name="get_user_interactions", read_only=True)

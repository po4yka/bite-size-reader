"""User and interaction operations for Database facade."""
# mypy: disable-error-code=attr-defined

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import peewee

from app.core.time_utils import UTC
from app.db.models import Chat, User, UserInteraction, model_to_dict

if TYPE_CHECKING:
    from collections.abc import Mapping


class DatabaseUserOpsMixin:
    """User/chat upsert and user interaction operations."""

    def upsert_user(
        self, *, telegram_user_id: int, username: str | None = None, is_owner: bool = False
    ) -> None:
        User.insert(
            telegram_user_id=telegram_user_id,
            username=username,
            is_owner=is_owner,
        ).on_conflict(
            conflict_target=[User.telegram_user_id],
            update={"username": username, "is_owner": is_owner},
        ).execute()

    def upsert_chat(
        self,
        *,
        chat_id: int,
        type_: str,
        title: str | None = None,
        username: str | None = None,
    ) -> None:
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

    def insert_user_interaction(
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
        self._logger.debug(
            "db_user_interaction_inserted",
            extra={
                "interaction_id": created.id,
                "user_id": user_id,
                "interaction_type": interaction_type,
            },
        )
        return created.id

    def update_user_interaction(
        self,
        interaction_id: int,
        *,
        updates: Mapping[str, Any] | None = None,
        response_sent: bool | None = None,
        response_type: str | None = None,
        error_occurred: bool | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        request_id: int | None = None,
    ) -> None:
        legacy_fields = (
            response_sent,
            response_type,
            error_occurred,
            error_message,
            processing_time_ms,
            request_id,
        )
        if updates and any(f is not None for f in legacy_fields):
            msg = "Cannot mix explicit field arguments with the updates mapping"
            raise ValueError(msg)

        update_values: dict[Any, Any] = {}
        if updates:
            invalid_fields = [
                key
                for key in updates
                if not isinstance(getattr(UserInteraction, key, None), peewee.Field)
            ]
            if invalid_fields:
                msg = f"Unknown user interaction fields: {', '.join(invalid_fields)}"
                raise ValueError(msg)
            for key, value in updates.items():
                field_obj = getattr(UserInteraction, key)
                update_values[field_obj] = value

        if response_sent is not None:
            update_values[UserInteraction.response_sent] = response_sent
        if response_type is not None:
            update_values[UserInteraction.response_type] = response_type
        if error_occurred is not None:
            update_values[UserInteraction.error_occurred] = error_occurred
        if error_message is not None:
            update_values[UserInteraction.error_message] = error_message
        if processing_time_ms is not None:
            update_values[UserInteraction.processing_time_ms] = processing_time_ms
        if request_id is not None:
            update_values[UserInteraction.request] = request_id

        if not update_values:
            return

        updated_at_field = getattr(UserInteraction, "updated_at", None)
        if isinstance(updated_at_field, peewee.Field):
            try:
                columns = {
                    column.name
                    for column in self._database.get_columns(UserInteraction._meta.table_name)
                }
            except (peewee.DatabaseError, AttributeError):
                columns = set()
            if updated_at_field.column_name in columns:
                update_values[updated_at_field] = dt.datetime.now(UTC)

        with self._database.connection_context():
            UserInteraction.update(update_values).where(
                UserInteraction.id == interaction_id
            ).execute()

    async def async_update_user_interaction(
        self,
        interaction_id: int,
        *,
        updates: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> None:
        """Async wrapper for :meth:`update_user_interaction`."""
        await self._safe_db_operation(
            self.update_user_interaction,
            interaction_id,
            updates=updates,
            operation_name="update_user_interaction",
            **fields,
        )

    def get_user_interactions(
        self,
        *,
        uid: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent user interactions for a user."""
        interactions = (
            UserInteraction.select()
            .where(UserInteraction.user_id == uid)
            .order_by(UserInteraction.created_at.desc())
            .limit(limit)
        )
        return [model_to_dict(interaction) for interaction in interactions]

"""Telegram message persistence for the SQLite request repository."""

from __future__ import annotations

from typing import Any

import peewee

from app.db.json_utils import prepare_json_payload
from app.db.models import Request, TelegramMessage, model_to_dict

from ._repository_mixin_base import SqliteRepositoryMixinBase


class RequestRepositoryTelegramMixin(SqliteRepositoryMixinBase):
    """Telegram-specific request persistence methods."""

    async def async_get_request_by_telegram_message(
        self,
        *,
        user_id: int,
        message_id: int,
    ) -> dict[str, Any] | None:
        """Return a user's request matched by bot reply or input message ID."""

        def _query() -> dict[str, Any] | None:
            request = (
                Request.select()
                .where(
                    (Request.user_id == user_id)
                    & (
                        (Request.bot_reply_message_id == message_id)
                        | (Request.input_message_id == message_id)
                    )
                )
                .order_by(Request.created_at.desc())
                .first()
            )
            return model_to_dict(request)

        return await self._execute(
            _query,
            operation_name="get_request_by_telegram_message",
            read_only=True,
        )

    async def async_insert_telegram_message(
        self,
        *,
        request_id: int,
        message_id: int | None,
        chat_id: int | None,
        date_ts: int | None,
        text_full: str | None,
        entities_json: Any,
        media_type: str | None,
        media_file_ids_json: Any,
        forward_from_chat_id: int | None,
        forward_from_chat_type: str | None,
        forward_from_chat_title: str | None,
        forward_from_message_id: int | None,
        forward_date_ts: int | None,
        telegram_raw_json: Any,
    ) -> int:
        """Insert a Telegram message snapshot."""

        def _insert() -> int:
            try:
                message = TelegramMessage.create(
                    request=request_id,
                    message_id=message_id,
                    chat_id=chat_id,
                    date_ts=date_ts,
                    text_full=text_full,
                    entities_json=prepare_json_payload(entities_json),
                    media_type=media_type,
                    media_file_ids_json=prepare_json_payload(media_file_ids_json),
                    forward_from_chat_id=forward_from_chat_id,
                    forward_from_chat_type=forward_from_chat_type,
                    forward_from_chat_title=forward_from_chat_title,
                    forward_from_message_id=forward_from_message_id,
                    forward_date_ts=forward_date_ts,
                    telegram_raw_json=prepare_json_payload(telegram_raw_json),
                )
                return message.id
            except peewee.IntegrityError:
                existing = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
                if existing:
                    return existing.id
                raise

        return await self._execute(_insert, operation_name="insert_telegram_message")

    async def async_update_bot_reply_message_id(
        self, request_id: int, bot_reply_message_id: int
    ) -> None:
        """Persist the Telegram message-id of the bot's reply."""

        def _update() -> None:
            Request.update(bot_reply_message_id=bot_reply_message_id).where(
                Request.id == request_id
            ).execute()

        await self._execute(_update, operation_name="update_bot_reply_message_id")

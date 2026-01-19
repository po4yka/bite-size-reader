"""SQLite implementation of Telegram message repository.

This adapter handles persistence of Telegram message snapshots including
text, entities, media, and forward information.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import peewee

from app.db.json_utils import prepare_json_payload
from app.db.models import TelegramMessage, model_to_dict
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository

JSONValue = Mapping[str, Any] | Sequence[Any] | str | None


class SqliteTelegramMessageRepositoryAdapter(SqliteBaseRepository):
    """Adapter for Telegram message persistence operations.

    This repository handles storing complete snapshots of Telegram messages
    for debugging, analytics, and message replay purposes.
    """

    async def async_insert_telegram_message(
        self,
        *,
        request_id: int,
        message_id: int | None,
        chat_id: int | None,
        date_ts: int | None,
        text_full: str | None,
        entities_json: JSONValue,
        media_type: str | None,
        media_file_ids_json: JSONValue,
        forward_from_chat_id: int | None,
        forward_from_chat_type: str | None,
        forward_from_chat_title: str | None,
        forward_from_message_id: int | None,
        forward_date_ts: int | None,
        telegram_raw_json: JSONValue,
    ) -> int:
        """Insert a Telegram message snapshot.

        Args:
            request_id: ID of the associated request
            message_id: Telegram message ID
            chat_id: Chat ID where message was received
            date_ts: Unix timestamp of message
            text_full: Full text content of the message
            entities_json: Message entities (mentions, URLs, etc.)
            media_type: Type of media if any (photo, video, document, etc.)
            media_file_ids_json: File IDs for media attachments
            forward_from_chat_id: Original chat ID if forwarded
            forward_from_chat_type: Original chat type if forwarded
            forward_from_chat_title: Original chat title if forwarded
            forward_from_message_id: Original message ID if forwarded
            forward_date_ts: Original timestamp if forwarded
            telegram_raw_json: Raw Telegram message JSON for debugging

        Returns:
            ID of the inserted message record

        Raises:
            peewee.IntegrityError: If a message for this request already exists
        """

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
                # Message already exists for this request - return existing ID
                existing = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
                if existing:
                    return existing.id
                raise

        return await self._execute(_insert, operation_name="insert_telegram_message")

    async def async_get_telegram_message_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get the Telegram message for a request.

        Args:
            request_id: ID of the request

        Returns:
            Message data as dict, or None if not found
        """

        def _get() -> dict[str, Any] | None:
            message = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
            return model_to_dict(message)

        return await self._execute(
            _get, operation_name="get_telegram_message_by_request", read_only=True
        )

    async def async_get_telegram_messages_for_user(
        self, user_id: int, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get recent Telegram messages for a user.

        Args:
            user_id: User ID to query
            limit: Maximum number of messages to return

        Returns:
            List of message dictionaries
        """
        from peewee import JOIN

        from app.db.models import Request

        def _get() -> list[dict[str, Any]]:
            messages = (
                TelegramMessage.select(TelegramMessage, Request)
                .join(Request, JOIN.INNER)
                .where(Request.user_id == user_id)
                .order_by(TelegramMessage.id.desc())
                .limit(limit)
            )
            return [model_to_dict(msg) or {} for msg in messages]

        return await self._execute(
            _get, operation_name="get_telegram_messages_for_user", read_only=True
        )

    async def async_get_forward_info(self, request_id: int) -> dict[str, Any] | None:
        """Get forward-related information for a request.

        Returns a dict with forward fields if the message was forwarded,
        or None if not found or not a forward.

        Args:
            request_id: ID of the request

        Returns:
            Forward info dict or None
        """

        def _get() -> dict[str, Any] | None:
            message = TelegramMessage.get_or_none(TelegramMessage.request == request_id)
            if not message or not message.forward_from_chat_id:
                return None

            return {
                "forward_from_chat_id": message.forward_from_chat_id,
                "forward_from_chat_type": message.forward_from_chat_type,
                "forward_from_chat_title": message.forward_from_chat_title,
                "forward_from_message_id": message.forward_from_message_id,
                "forward_date_ts": message.forward_date_ts,
            }

        return await self._execute(_get, operation_name="get_forward_info", read_only=True)

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all Telegram messages for a user (for sync operations).

        Returns:
            List of message dicts with request_id flattened.
        """
        from peewee import JOIN

        from app.db.models import Request

        def _get() -> list[dict[str, Any]]:
            messages = (
                TelegramMessage.select(TelegramMessage, Request)
                .join(Request, JOIN.INNER)
                .where(Request.user_id == user_id)
            )
            result = []
            for msg in messages:
                m_dict = model_to_dict(msg) or {}
                # Flatten request to just the ID for sync
                if "request" in m_dict and isinstance(m_dict["request"], dict):
                    m_dict["request"] = m_dict["request"]["id"]
                result.append(m_dict)
            return result

        return await self._execute(
            _get, operation_name="get_all_telegram_messages_for_user", read_only=True
        )

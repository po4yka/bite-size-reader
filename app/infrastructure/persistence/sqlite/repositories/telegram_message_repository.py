"""SQLAlchemy implementation of the Telegram message repository."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.json_utils import prepare_json_payload
from app.db.models import Request, TelegramMessage, model_to_dict

if TYPE_CHECKING:
    from app.db.session import Database

JSONValue = Mapping[str, Any] | Sequence[Any] | str | None


class SqliteTelegramMessageRepositoryAdapter:
    """Adapter for Telegram message persistence operations using SQLAlchemy."""

    def __init__(self, database: Database) -> None:
        self._database = database

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
        """Insert a Telegram message snapshot and return the existing ID on conflict."""
        payload = {
            "request_id": request_id,
            "message_id": message_id,
            "chat_id": chat_id,
            "date_ts": date_ts,
            "text_full": text_full,
            "entities_json": prepare_json_payload(entities_json),
            "media_type": media_type,
            "media_file_ids_json": prepare_json_payload(media_file_ids_json),
            "forward_from_chat_id": forward_from_chat_id,
            "forward_from_chat_type": forward_from_chat_type,
            "forward_from_chat_title": forward_from_chat_title,
            "forward_from_message_id": forward_from_message_id,
            "forward_date_ts": forward_date_ts,
            "telegram_raw_json": prepare_json_payload(telegram_raw_json),
        }
        async with self._database.transaction() as session:
            stmt = (
                insert(TelegramMessage)
                .values(**payload)
                .on_conflict_do_nothing(index_elements=[TelegramMessage.request_id])
                .returning(TelegramMessage.id)
            )
            inserted_id = await session.scalar(stmt)
            if inserted_id is not None:
                return int(inserted_id)
            existing_id = await session.scalar(
                select(TelegramMessage.id).where(TelegramMessage.request_id == request_id)
            )
            if existing_id is None:
                msg = f"telegram message conflict for request_id={request_id} but no row exists"
                raise RuntimeError(msg)
            return int(existing_id)

    async def async_get_telegram_message_by_request(self, request_id: int) -> dict[str, Any] | None:
        """Get the Telegram message for a request."""
        async with self._database.session() as session:
            message = await session.scalar(
                select(TelegramMessage).where(TelegramMessage.request_id == request_id)
            )
            return model_to_dict(message)

    async def async_get_telegram_messages_for_user(
        self, user_id: int, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get recent Telegram messages for a user."""
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(TelegramMessage)
                    .join(Request, TelegramMessage.request_id == Request.id)
                    .where(Request.user_id == user_id)
                    .order_by(TelegramMessage.id.desc())
                    .limit(limit)
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]

    async def async_get_forward_info(self, request_id: int) -> dict[str, Any] | None:
        """Get forward-related information for a request."""
        async with self._database.session() as session:
            message = await session.scalar(
                select(TelegramMessage).where(TelegramMessage.request_id == request_id)
            )
            if message is None or not message.forward_from_chat_id:
                return None
            return {
                "forward_from_chat_id": message.forward_from_chat_id,
                "forward_from_chat_type": message.forward_from_chat_type,
                "forward_from_chat_title": message.forward_from_chat_title,
                "forward_from_message_id": message.forward_from_message_id,
                "forward_date_ts": message.forward_date_ts,
            }

    async def async_get_all_for_user(self, user_id: int) -> list[dict[str, Any]]:
        """Get all Telegram messages for a user."""
        async with self._database.session() as session:
            rows = (
                await session.execute(
                    select(TelegramMessage)
                    .join(Request, TelegramMessage.request_id == Request.id)
                    .where(Request.user_id == user_id)
                    .order_by(TelegramMessage.id)
                )
            ).scalars()
            return [model_to_dict(row) or {} for row in rows]

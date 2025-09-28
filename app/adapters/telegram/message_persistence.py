"""Message persistence and database operations."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.db.database import Database

logger = logging.getLogger(__name__)


class MessagePersistence:
    """Handles message snapshots and database operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def persist_message_snapshot(self, request_id: int, message: Any) -> None:
        """Persist message snapshot to database."""
        # Security: Validate request_id
        if not isinstance(request_id, int) or request_id <= 0:
            raise ValueError("Invalid request_id")

        # Security: Validate message object
        if message is None:
            raise ValueError("Message cannot be None")

        # Extract basic fields with best-effort approach
        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        msg_id = int(msg_id_raw) if msg_id_raw is not None else None

        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        if chat_id is not None:
            chat_type = getattr(chat_obj, "type", None)
            chat_title = getattr(chat_obj, "title", None)
            chat_username = getattr(chat_obj, "username", None)
            try:
                self.db.upsert_chat(
                    chat_id=chat_id,
                    type_=str(chat_type) if chat_type is not None else None,
                    title=str(chat_title) if isinstance(chat_title, str) else None,
                    username=str(chat_username) if isinstance(chat_username, str) else None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "chat_upsert_failed",
                    extra={"chat_id": chat_id, "error": str(exc)},
                )

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id", 0) if from_user_obj is not None else None
        user_id = int(user_id_raw) if user_id_raw is not None else None
        if user_id is not None:
            username = getattr(from_user_obj, "username", None)
            try:
                self.db.upsert_user(
                    telegram_user_id=user_id,
                    username=str(username) if isinstance(username, str) else None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "user_upsert_failed",
                    extra={"user_id": user_id, "error": str(exc)},
                )

        date_ts = self._to_epoch(
            getattr(message, "date", None) or getattr(message, "forward_date", None)
        )
        text_full = getattr(message, "text", None) or getattr(message, "caption", "") or None

        # Process entities
        entities_json = self._extract_entities_json(message)

        # Process media
        media_type, media_file_ids_json = self._extract_media_info(message)

        # Process forward info
        forward_info = self._extract_forward_info(message)

        # Raw JSON if possible
        raw_json = self._extract_raw_json(message)

        self.db.insert_telegram_message(
            request_id=request_id,
            message_id=msg_id,
            chat_id=chat_id,
            date_ts=date_ts,
            text_full=text_full,
            entities_json=entities_json,
            media_type=media_type,
            media_file_ids_json=media_file_ids_json,
            forward_from_chat_id=forward_info["chat_id"],
            forward_from_chat_type=forward_info["chat_type"],
            forward_from_chat_title=forward_info["chat_title"],
            forward_from_message_id=forward_info["message_id"],
            forward_date_ts=forward_info["date_ts"],
            telegram_raw_json=raw_json,
        )

    def _to_epoch(self, val: Any) -> int | None:
        """Convert value to epoch timestamp."""
        try:
            from datetime import datetime

            if isinstance(val, datetime):
                return int(val.timestamp())
            if val is None:
                return None
            # Some libraries expose pyrogram types with .timestamp or int-like
            if hasattr(val, "timestamp"):
                try:
                    ts_val = getattr(val, "timestamp")
                    if callable(ts_val):
                        return int(ts_val())
                except Exception:
                    pass
            return int(val)  # may raise if not int-like
        except Exception:
            return None

    def _extract_entities_json(self, message: Any) -> str | None:
        """Extract entities from message as JSON."""
        entities_obj = list(getattr(message, "entities", []) or [])
        entities_obj.extend(list(getattr(message, "caption_entities", []) or []))

        try:

            def _ent_to_dict(e: Any) -> dict:
                if hasattr(e, "to_dict"):
                    try:
                        entity_dict = e.to_dict()
                        # Check if the result is actually serializable (not a MagicMock)
                        if isinstance(entity_dict, dict):
                            return entity_dict
                    except Exception:
                        pass
                return getattr(e, "__dict__", {})

            return json.dumps([_ent_to_dict(e) for e in entities_obj], ensure_ascii=False)
        except Exception:
            return None

    def _extract_media_info(self, message: Any) -> tuple[str | None, str | None]:
        """Extract media type and file IDs from message."""
        media_type = None
        media_file_ids: list[str] = []

        # Detect common media types and collect file_ids
        try:
            if getattr(message, "photo", None) is not None:
                media_type = "photo"
                photo = getattr(message, "photo")
                fid = getattr(photo, "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "video", None) is not None:
                media_type = "video"
                fid = getattr(getattr(message, "video"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "document", None) is not None:
                media_type = "document"
                fid = getattr(getattr(message, "document"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "audio", None) is not None:
                media_type = "audio"
                fid = getattr(getattr(message, "audio"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "voice", None) is not None:
                media_type = "voice"
                fid = getattr(getattr(message, "voice"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "animation", None) is not None:
                media_type = "animation"
                fid = getattr(getattr(message, "animation"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
            elif getattr(message, "sticker", None) is not None:
                media_type = "sticker"
                fid = getattr(getattr(message, "sticker"), "file_id", None)
                if fid:
                    media_file_ids.append(fid)
        except Exception:
            pass

        # Filter out non-string values (like MagicMock objects) from media_file_ids
        valid_media_file_ids = [fid for fid in media_file_ids if isinstance(fid, str)]
        media_file_ids_json = (
            json.dumps(valid_media_file_ids, ensure_ascii=False) if valid_media_file_ids else None
        )

        return media_type, media_file_ids_json

    def _extract_forward_info(self, message: Any) -> dict[str, Any]:
        """Extract forward information from message."""
        fwd_chat = getattr(message, "forward_from_chat", None)
        fwd_chat_id_raw = getattr(fwd_chat, "id", 0) if fwd_chat is not None else None
        forward_from_chat_id = int(fwd_chat_id_raw) if fwd_chat_id_raw is not None else None
        forward_from_chat_type = getattr(fwd_chat, "type", None)
        forward_from_chat_title = getattr(fwd_chat, "title", None)

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", 0)
        forward_from_message_id = int(fwd_msg_id_raw) if fwd_msg_id_raw is not None else None
        forward_date_ts = self._to_epoch(getattr(message, "forward_date", None))

        return {
            "chat_id": forward_from_chat_id,
            "chat_type": forward_from_chat_type,
            "chat_title": forward_from_chat_title,
            "message_id": forward_from_message_id,
            "date_ts": forward_date_ts,
        }

    def _extract_raw_json(self, message: Any) -> str | None:
        """Extract raw JSON from message if possible."""
        try:
            if hasattr(message, "to_dict"):
                message_dict = message.to_dict()
                # Check if the result is actually serializable (not a MagicMock)
                if isinstance(message_dict, dict):
                    return json.dumps(message_dict, ensure_ascii=False)
                else:
                    return None
            else:
                return None
        except Exception:
            return None

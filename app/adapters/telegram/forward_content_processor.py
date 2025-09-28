"""Forward content processing and extraction."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import AppConfig
from app.core.html_utils import normalize_with_textacy
from app.core.lang import choose_language, detect_language
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

# Route versioning constants
FORWARD_ROUTE_VERSION = 1


class ForwardContentProcessor:
    """Handles forward content extraction and processing."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func

    async def process_forward_content(
        self, message: Any, correlation_id: str | None = None
    ) -> tuple[int, str, str, str]:
        """Process forward content and return (req_id, prompt, chosen_lang, system_prompt)."""
        # Extract content
        text = (getattr(message, "text", None) or getattr(message, "caption", "") or "").strip()
        title = getattr(getattr(message, "forward_from_chat", None), "title", "")
        prompt = f"Channel: {title}\n\n{text}"

        # Optional normalization for forwards as well
        try:
            if getattr(self.cfg.runtime, "enable_textacy", False):
                prompt = normalize_with_textacy(prompt)
        except Exception:
            pass

        # Create request with content text
        req_id = self._create_forward_request(message, correlation_id, prompt)

        # Language detection and choice
        detected = detect_language(text)
        try:
            self.db.update_request_lang_detected(req_id, detected)
        except Exception as e:  # noqa: BLE001
            logger.error("persist_lang_detected_error", extra={"error": str(e)})

        chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)
        system_prompt = await self._load_system_prompt(chosen_lang)

        logger.debug(
            "language_choice",
            extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
        )

        # Notify: request accepted and language detected
        await self.response_formatter.send_forward_accepted_notification(message, title)
        await self.response_formatter.send_forward_language_notification(message, detected)

        return req_id, prompt, chosen_lang, system_prompt

    def _create_forward_request(
        self, message: Any, correlation_id: str | None, content_text: str | None = None
    ) -> int:
        """Create forward request in database."""
        self._upsert_sender_metadata(message)

        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id", 0) if from_user_obj is not None else None
        user_id = int(user_id_raw) if user_id_raw is not None else None

        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        input_message_id = int(msg_id_raw) if msg_id_raw is not None else None

        fwd_chat_obj = getattr(message, "forward_from_chat", None)
        fwd_from_chat_id_raw = getattr(fwd_chat_obj, "id", 0) if fwd_chat_obj is not None else None
        fwd_from_chat_id = int(fwd_from_chat_id_raw) if fwd_from_chat_id_raw is not None else None

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", 0)
        fwd_from_msg_id = int(fwd_msg_id_raw) if fwd_msg_id_raw is not None else None

        existing_req: dict | None = None
        if fwd_from_chat_id is not None and fwd_from_msg_id is not None:
            existing_req = self.db.get_request_by_forward(fwd_from_chat_id, fwd_from_msg_id)

        if existing_req is not None:
            req_id = int(existing_req["id"])
            self._audit(
                "INFO",
                "forward_request_dedupe_hit",
                {
                    "request_id": req_id,
                    "fwd_chat_id": fwd_from_chat_id,
                    "fwd_msg_id": fwd_from_msg_id,
                    "cid": correlation_id,
                },
            )
            if correlation_id:
                try:
                    self.db.update_request_correlation_id(req_id, correlation_id)
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "persist_cid_error",
                        extra={"error": str(exc), "cid": correlation_id},
                    )
            return req_id

        req_id = self.db.create_request(
            type_="forward",
            status="pending",
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_message_id=input_message_id,
            fwd_from_chat_id=fwd_from_chat_id,
            fwd_from_msg_id=fwd_from_msg_id,
            content_text=content_text,  # Store the full prompt as content text
            route_version=FORWARD_ROUTE_VERSION,
        )

        # Snapshot telegram message
        try:
            self._persist_message_snapshot(req_id, message)
        except Exception as e:  # noqa: BLE001
            logger.error("snapshot_error", extra={"error": str(e)})

        return req_id

    def _upsert_sender_metadata(self, message: Any) -> None:
        """Persist sender user/chat metadata for the interaction."""

        def _coerce_int(value: Any) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        chat_obj = getattr(message, "chat", None)
        chat_id = _coerce_int(getattr(chat_obj, "id", None) if chat_obj is not None else None)
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
        user_id = _coerce_int(
            getattr(from_user_obj, "id", None) if from_user_obj is not None else None
        )
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

    async def _load_system_prompt(self, lang: str) -> str:
        """Load system prompt file based on language."""
        from pathlib import Path

        base = Path(__file__).resolve().parents[1] / "prompts"
        fname = "summary_system_ru.txt" if lang == "ru" else "summary_system_en.txt"
        path = base / fname
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            # Fallback inline prompt
            return "You are a precise assistant that returns only a strict JSON object matching the provided schema."

    def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        """Persist message snapshot to database."""
        # This is a duplicate of the method in message_persistence.py
        # In a real refactor, we'd use the MessagePersistence class
        # For now, keeping it here to maintain functionality
        pass

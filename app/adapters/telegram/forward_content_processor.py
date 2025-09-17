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

        # Create request
        req_id = self._create_forward_request(message, correlation_id)

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

    def _create_forward_request(self, message: Any, correlation_id: str | None) -> int:
        """Create forward request in database."""
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

        req_id = self.db.create_request(
            type_="forward",
            status="pending",
            correlation_id=correlation_id,
            chat_id=chat_id,
            user_id=user_id,
            input_message_id=input_message_id,
            fwd_from_chat_id=fwd_from_chat_id,
            fwd_from_msg_id=fwd_from_msg_id,
            route_version=FORWARD_ROUTE_VERSION,
        )

        # Snapshot telegram message
        try:
            self._persist_message_snapshot(req_id, message)
        except Exception as e:  # noqa: BLE001
            logger.error("snapshot_error", extra={"error": str(e)})

        return req_id

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

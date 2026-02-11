"""Forward content processing and extraction."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.html_utils import normalize_text
from app.core.lang import choose_language, detect_language
from app.infrastructure.persistence.message_persistence import MessagePersistence
from app.prompts.manager import get_prompt_manager

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager

logger = logging.getLogger(__name__)


def _coerce_int(value: Any) -> int | None:
    """Safely coerce a value to int, returning None on failure."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


# Forward processing route version
FORWARD_ROUTE_VERSION = 1


class ForwardContentProcessor:
    """Handles forward content extraction and processing."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func
        self.message_persistence = MessagePersistence(db)

    async def process_forward_content(
        self, message: Any, correlation_id: str | None = None
    ) -> tuple[int, str, str, str]:
        """Process forward content and return (req_id, prompt, chosen_lang, system_prompt)."""
        # Extract content
        text = (getattr(message, "text", None) or getattr(message, "caption", "") or "").strip()

        # Determine source attribution: channel title, user name, or sender name
        fwd_chat = getattr(message, "forward_from_chat", None)
        title = getattr(fwd_chat, "title", "") if fwd_chat is not None else ""
        if not title:
            fwd_user = getattr(message, "forward_from", None)
            if fwd_user is not None:
                first = getattr(fwd_user, "first_name", "") or ""
                last = getattr(fwd_user, "last_name", "") or ""
                title = f"{first} {last}".strip()
            if not title:
                title = getattr(message, "forward_sender_name", "") or ""

        source_label = "Channel" if fwd_chat is not None else "Source"
        prompt = f"{source_label}: {title}\n\n{text}" if title else text

        if not text:
            logger.warning(
                "forward_empty_text",
                extra={"cid": correlation_id, "source": title},
            )
            await self.response_formatter.safe_reply(
                message,
                "This forwarded message has no text content to summarize. "
                "Please forward a message that contains text.",
            )
            raise ValueError("Forwarded message has no text content")

        # Optional normalization for forwards as well
        try:
            if getattr(self.cfg.runtime, "enable_textacy", False):
                prompt = normalize_text(prompt)
        except Exception:
            logger.debug("forward_text_normalize_failed", exc_info=True)

        # Create request with content text
        req_id = await self._create_forward_request(message, correlation_id, prompt)

        # Language detection and choice
        detected = detect_language(text)
        # Graceful degradation: if persisting the detected language fails, the
        # in-memory `detected` value is still used for prompt selection. The DB
        # record may show NULL for lang_detected, which is acceptable.
        try:
            await self.message_persistence.request_repo.async_update_request_lang_detected(
                req_id, detected
            )
        except Exception as e:
            logger.exception("persist_lang_detected_error", extra={"error": str(e)})

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

    async def _create_forward_request(
        self, message: Any, correlation_id: str | None, content_text: str | None = None
    ) -> int:
        """Create forward request in database."""
        await self._upsert_sender_metadata(message)

        chat_obj = getattr(message, "chat", None)
        chat_id = _coerce_int(getattr(chat_obj, "id", None) if chat_obj is not None else None)

        from_user_obj = getattr(message, "from_user", None)
        user_id = _coerce_int(
            getattr(from_user_obj, "id", None) if from_user_obj is not None else None
        )

        msg_id_raw = getattr(message, "id", getattr(message, "message_id", None))
        input_message_id = _coerce_int(msg_id_raw)

        fwd_chat_obj = getattr(message, "forward_from_chat", None)
        fwd_from_chat_id = _coerce_int(
            getattr(fwd_chat_obj, "id", None) if fwd_chat_obj is not None else None
        )

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", None)
        fwd_from_msg_id = _coerce_int(fwd_msg_id_raw)

        # Deduplication only applies to channel forwards where both fwd_from_chat_id
        # and fwd_from_msg_id are available. User/privacy forwards (where Telegram
        # strips the origin) intentionally create a new request each time.
        existing_req: dict | None = None
        if fwd_from_chat_id is not None and fwd_from_msg_id is not None:
            existing_req = await self.message_persistence.request_repo.async_get_request_by_forward(
                fwd_from_chat_id, fwd_from_msg_id
            )

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
                    await self.message_persistence.request_repo.async_update_request_correlation_id(
                        req_id, correlation_id
                    )
                except Exception as exc:
                    logger.exception(
                        "persist_cid_error",
                        extra={"error": str(exc), "cid": correlation_id},
                    )
            return req_id

        req_id = await self.message_persistence.request_repo.async_create_request(
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
            await self._persist_message_snapshot(req_id, message)
        except Exception as e:
            logger.exception("snapshot_error", extra={"error": str(e)})

        return req_id

    async def _upsert_sender_metadata(self, message: Any) -> None:
        """Persist sender user/chat metadata for the interaction."""
        chat_obj = getattr(message, "chat", None)
        chat_id = _coerce_int(getattr(chat_obj, "id", None) if chat_obj is not None else None)
        if chat_id is not None:
            chat_type = getattr(chat_obj, "type", None)
            chat_title = getattr(chat_obj, "title", None)
            chat_username = getattr(chat_obj, "username", None)
            try:
                await self.message_persistence.user_repo.async_upsert_chat(
                    chat_id=chat_id,
                    type_=str(chat_type) if chat_type is not None else None,
                    title=str(chat_title) if isinstance(chat_title, str) else None,
                    username=str(chat_username) if isinstance(chat_username, str) else None,
                )
            except Exception as exc:
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
                await self.message_persistence.user_repo.async_upsert_user(
                    telegram_user_id=user_id,
                    username=str(username) if isinstance(username, str) else None,
                )
            except Exception as exc:
                logger.warning(
                    "user_upsert_failed",
                    extra={"user_id": user_id, "error": str(exc)},
                )

    async def _load_system_prompt(self, lang: str) -> str:
        """Load system prompt file based on language using PromptManager.

        Uses the unified PromptManager for prompt loading, caching, validation,
        and optional few-shot example injection.

        Args:
            lang: Language code ('en' or 'ru')

        Returns:
            System prompt text with optional examples
        """
        try:
            manager = get_prompt_manager()
            return manager.get_system_prompt(lang, include_examples=True, num_examples=2)
        except Exception:
            # Fallback inline prompt
            return "You are a precise assistant that returns only a strict JSON object matching the provided schema."

    async def _persist_message_snapshot(self, request_id: int, message: Any) -> None:
        """Persist message snapshot to database."""
        await self.message_persistence.persist_message_snapshot(request_id, message)

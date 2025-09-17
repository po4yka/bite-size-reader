# ruff: noqa: E501
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from app.config import AppConfig
from app.core.html_utils import normalize_with_textacy
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU, choose_language, detect_language
from app.core.summary_contract import validate_and_shape_summary
from app.db.database import Database
from app.utils.json_validation import parse_summary_response

if TYPE_CHECKING:
    from app.adapters.openrouter_client import OpenRouterClient
    from app.adapters.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

# Route versioning constants
FORWARD_ROUTE_VERSION = 1


class ForwardProcessor:
    """Handles forwarded message processing and AI summarization."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        openrouter: OpenRouterClient,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem

    async def handle_forward_flow(
        self, message: Any, *, correlation_id: str | None = None, interaction_id: int | None = None
    ) -> None:
        """Handle complete forwarded message processing flow."""
        text = (getattr(message, "text", None) or getattr(
            message, "caption", "") or "").strip()
        title = getattr(
            getattr(message, "forward_from_chat", None), "title", "")
        prompt = f"Channel: {title}\n\n{text}"

        # Optional normalization for forwards as well
        try:
            if getattr(self.cfg.runtime, "enable_textacy", False):
                prompt = normalize_with_textacy(prompt)
        except Exception:
            pass

        # Create request row (pending)
        chat_obj = getattr(message, "chat", None)
        chat_id_raw = getattr(
            chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        from_user_obj = getattr(message, "from_user", None)
        user_id_raw = getattr(from_user_obj, "id",
                              0) if from_user_obj is not None else None
        user_id = int(user_id_raw) if user_id_raw is not None else None

        msg_id_raw = getattr(message, "id", getattr(message, "message_id", 0))
        input_message_id = int(msg_id_raw) if msg_id_raw is not None else None

        fwd_chat_obj = getattr(message, "forward_from_chat", None)
        fwd_from_chat_id_raw = getattr(
            fwd_chat_obj, "id", 0) if fwd_chat_obj is not None else None
        fwd_from_chat_id = int(
            fwd_from_chat_id_raw) if fwd_from_chat_id_raw is not None else None

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", 0)
        fwd_from_msg_id = int(
            fwd_msg_id_raw) if fwd_msg_id_raw is not None else None

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

        # Notify: request accepted (forward) with enhanced info
        await self.response_formatter.send_forward_accepted_notification(message, title)

        # Language detection and choice
        detected = detect_language(text)
        try:
            self.db.update_request_lang_detected(req_id, detected)
        except Exception as e:  # noqa: BLE001
            logger.error("persist_lang_detected_error",
                         extra={"error": str(e)})
        chosen_lang = choose_language(
            self.cfg.runtime.preferred_lang, detected)
        system_prompt = await self._load_system_prompt(chosen_lang)
        logger.debug(
            "language_choice",
            extra={"detected": detected,
                   "chosen": chosen_lang, "cid": correlation_id},
        )

        # Notify: language detected (forward) with enhanced info
        await self.response_formatter.send_forward_language_notification(message, detected)

        # LLM - truncate content if too long
        max_content_length = 45000  # Leave some buffer for the prompt
        if len(prompt) > max_content_length:
            prompt = prompt[:max_content_length] + \
                "\n\n[Content truncated due to length]"
            logger.warning(
                "content_truncated",
                extra={
                    "original_length": len(prompt),
                    "truncated_length": max_content_length,
                    "cid": correlation_id,
                },
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Summarize the following message to the specified JSON schema. "
                    f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n{prompt}"
                ),
            },
        ]
        async with self._sem():
            # Use enhanced structured output configuration for forwarded messages
            fwd_response_format = self._build_structured_response_format()

            llm = await self.openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=self.cfg.openrouter.max_tokens,
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
                response_format=fwd_response_format,
            )

        # Enhanced notification for forward completion
        await self.response_formatter.send_forward_completion_notification(message, llm)

        # Enhanced salvage logic for forward flow
        forward_salvage_shaped: dict[str, Any] | None = None
        if llm.status != "ok" and (llm.error_text or "") == "structured_output_parse_error":
            try:
                parsed = extract_json(llm.response_text or "")
                if isinstance(parsed, dict):
                    forward_salvage_shaped = validate_and_shape_summary(parsed)
                if forward_salvage_shaped is None:
                    pr = parse_summary_response(
                        llm.response_json, llm.response_text)
                    forward_salvage_shaped = pr.shaped

                if forward_salvage_shaped:
                    logger.info(
                        "forward_structured_output_salvage_success", extra={"cid": correlation_id}
                    )
            except Exception:
                forward_salvage_shaped = None

        if (llm.status != "ok" or not llm.response_text) and forward_salvage_shaped is None:
            # persist LLM call as error, then reply
            try:
                # json.dumps with default=str to avoid MagicMock serialization errors in tests
                self.db.insert_llm_call(
                    request_id=req_id,
                    provider="openrouter",
                    model=llm.model or self.cfg.openrouter.model,
                    endpoint=llm.endpoint,
                    request_headers_json=json.dumps(
                        llm.request_headers or {}, default=str),
                    request_messages_json=json.dumps(
                        llm.request_messages or [], default=str),
                    response_text=llm.response_text,
                    response_json=json.dumps(
                        llm.response_json or {}, default=str),
                    tokens_prompt=llm.tokens_prompt,
                    tokens_completion=llm.tokens_completion,
                    cost_usd=llm.cost_usd,
                    latency_ms=llm.latency_ms,
                    status=llm.status,
                    error_text=llm.error_text,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("persist_llm_error", extra={
                             "error": str(e), "cid": correlation_id})
            self.db.update_request_status(req_id, "error")
            await self.response_formatter.send_error_notification(
                message, "llm_error", correlation_id
            )
            logger.error("openrouter_error", extra={
                         "error": llm.error_text, "cid": correlation_id})
            try:
                self._audit(
                    "ERROR",
                    "openrouter_error",
                    {"request_id": req_id, "cid": correlation_id,
                        "error": llm.error_text},
                )
            except Exception:
                pass

            # Update interaction with error
            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message=f"LLM error: {llm.error_text or 'Unknown error'}",
                    request_id=req_id,
                )
            return

        # Enhanced parsing for forward flow
        forward_shaped: dict[str, Any] | None = forward_salvage_shaped

        if forward_shaped is None:
            try:
                extracted_fwd = extract_json(llm.response_text or "")
                if extracted_fwd is not None:
                    forward_shaped = validate_and_shape_summary(extracted_fwd)
            except Exception:
                forward_shaped = None

        if forward_shaped is None:
            parse_result = parse_summary_response(
                llm.response_json, llm.response_text)
            if parse_result and parse_result.shaped is not None:
                forward_shaped = parse_result.shaped
                if parse_result.used_local_fix:
                    logger.info(
                        "json_local_fix_applied",
                        extra={"cid": correlation_id,
                               "stage": "initial_forwarded"},
                    )
            else:
                # Enhanced repair for forward flow
                try:
                    logger.info(
                        "json_repair_attempt_forward_enhanced",
                        extra={
                            "cid": correlation_id,
                            "reason": parse_result.errors[-3:]
                            if parse_result and parse_result.errors
                            else None,
                            "structured_mode": self.cfg.openrouter.structured_output_mode,
                        },
                    )
                    repair_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": messages[1]["content"]},
                        {"role": "assistant", "content": llm.response_text or ""},
                        {
                            "role": "user",
                            "content": (
                                "Your previous message was not a valid JSON object. "
                                "Respond with ONLY a corrected JSON that matches the schema exactly."
                            ),
                        },
                    ]
                    async with self._sem():
                        fwd_repair_response_format = self._build_structured_response_format()
                        repair = await self.openrouter.chat(
                            repair_messages,
                            temperature=self.cfg.openrouter.temperature,
                            max_tokens=self.cfg.openrouter.max_tokens,
                            top_p=self.cfg.openrouter.top_p,
                            request_id=req_id,
                            response_format=fwd_repair_response_format,
                        )
                    if repair.status == "ok":
                        repair_result = parse_summary_response(
                            repair.response_json, repair.response_text
                        )
                        if repair_result.shaped is not None:
                            forward_shaped = repair_result.shaped
                            logger.info(
                                "json_repair_success_forward_enhanced",
                                extra={
                                    "cid": correlation_id,
                                    "used_local_fix": repair_result.used_local_fix,
                                },
                            )
                        else:
                            raise ValueError("repair_failed")
                    else:
                        raise ValueError("repair_call_error")
                except Exception:
                    self.db.update_request_status(req_id, "error")
                    await self.response_formatter.send_error_notification(
                        message, "processing_failed", correlation_id
                    )

                    # Update interaction with error
                    if interaction_id:
                        self._update_user_interaction(
                            interaction_id=interaction_id,
                            response_sent=True,
                            response_type="error",
                            error_occurred=True,
                            error_message="Invalid summary format",
                            request_id=req_id,
                        )
                    return

        if forward_shaped is None:
            self.db.update_request_status(req_id, "error")
            await self.response_formatter.send_error_notification(
                message, "processing_failed", correlation_id
            )

            if interaction_id:
                self._update_user_interaction(
                    interaction_id=interaction_id,
                    response_sent=True,
                    response_type="error",
                    error_occurred=True,
                    error_message="Invalid summary format",
                    request_id=req_id,
                )
            return

        try:
            self.db.insert_llm_call(
                request_id=req_id,
                provider="openrouter",
                model=llm.model or self.cfg.openrouter.model,
                endpoint=llm.endpoint,
                request_headers_json=json.dumps(llm.request_headers or {}),
                request_messages_json=json.dumps([m for m in messages]),
                response_text=llm.response_text,
                response_json=json.dumps(llm.response_json or {}),
                tokens_prompt=llm.tokens_prompt,
                tokens_completion=llm.tokens_completion,
                cost_usd=llm.cost_usd,
                latency_ms=llm.latency_ms,
                status=llm.status,
                error_text=llm.error_text,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("persist_llm_error", extra={
                         "error": str(e), "cid": correlation_id})

        try:
            new_version = self.db.upsert_summary(
                request_id=req_id, lang=chosen_lang, json_payload=json.dumps(
                    forward_shaped)
            )
            self.db.update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {
                        "request_id": req_id, "version": new_version})
        except Exception as e:  # noqa: BLE001
            logger.error("persist_summary_error", extra={
                         "error": str(e), "cid": correlation_id})

        # Update interaction with successful completion
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
            )

        # Enhanced preview for forward flow
        await self.response_formatter.send_forward_summary_response(message, forward_shaped)

    def _build_structured_response_format(self) -> dict[str, Any]:
        """Build response format configuration for structured outputs."""
        try:
            from app.core.summary_contract import get_summary_json_schema

            if self.cfg.openrouter.structured_output_mode == "json_schema":
                return {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "summary_schema",
                        "schema": get_summary_json_schema(),
                        "strict": True,
                    },
                }
            else:
                return {"type": "json_object"}
        except Exception:
            # Fallback to basic JSON object mode
            return {"type": "json_object"}

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
        chat_id_raw = getattr(
            chat_obj, "id", 0) if chat_obj is not None else None
        chat_id = int(chat_id_raw) if chat_id_raw is not None else None

        def _to_epoch(val: Any) -> int | None:
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

        date_ts = _to_epoch(
            getattr(message, "date", None) or getattr(
                message, "forward_date", None)
        )
        text_full = getattr(message, "text", None) or getattr(
            message, "caption", "") or None

        # Entities
        entities_obj = list(getattr(message, "entities", []) or [])
        entities_obj.extend(
            list(getattr(message, "caption_entities", []) or []))
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

            entities_json = json.dumps([_ent_to_dict(e)
                                       for e in entities_obj], ensure_ascii=False)
        except Exception:
            entities_json = None

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
        valid_media_file_ids = [
            fid for fid in media_file_ids if isinstance(fid, str)]
        media_file_ids_json = (
            json.dumps(valid_media_file_ids,
                       ensure_ascii=False) if valid_media_file_ids else None
        )

        # Forward info
        fwd_chat = getattr(message, "forward_from_chat", None)
        fwd_chat_id_raw = getattr(
            fwd_chat, "id", 0) if fwd_chat is not None else None
        forward_from_chat_id = int(
            fwd_chat_id_raw) if fwd_chat_id_raw is not None else None
        forward_from_chat_type = getattr(fwd_chat, "type", None)
        forward_from_chat_title = getattr(fwd_chat, "title", None)

        fwd_msg_id_raw = getattr(message, "forward_from_message_id", 0)
        forward_from_message_id = int(
            fwd_msg_id_raw) if fwd_msg_id_raw is not None else None
        forward_date_ts = _to_epoch(getattr(message, "forward_date", None))

        # Raw JSON if possible
        raw_json = None
        try:
            if hasattr(message, "to_dict"):
                message_dict = message.to_dict()
                # Check if the result is actually serializable (not a MagicMock)
                if isinstance(message_dict, dict):
                    raw_json = json.dumps(message_dict, ensure_ascii=False)
                else:
                    raw_json = None
            else:
                raw_json = None
        except Exception:
            raw_json = None

        self.db.insert_telegram_message(
            request_id=request_id,
            message_id=msg_id,
            chat_id=chat_id,
            date_ts=date_ts,
            text_full=text_full,
            entities_json=entities_json,
            media_type=media_type,
            media_file_ids_json=media_file_ids_json,
            forward_from_chat_id=forward_from_chat_id,
            forward_from_chat_type=forward_from_chat_type,
            forward_from_chat_title=forward_from_chat_title,
            forward_from_message_id=forward_from_message_id,
            forward_date_ts=forward_date_ts,
            telegram_raw_json=raw_json,
        )

    def _update_user_interaction(
        self,
        *,
        interaction_id: int,
        response_sent: bool | None = None,
        response_type: str | None = None,
        error_occurred: bool | None = None,
        error_message: str | None = None,
        processing_time_ms: int | None = None,
        request_id: int | None = None,
    ) -> None:
        """Update an existing user interaction record."""
        # Note: This method is a placeholder for future user interaction tracking
        # The current database schema doesn't include user_interactions table
        logger.debug(
            "user_interaction_update_placeholder",
            extra={"interaction_id": interaction_id,
                   "response_type": response_type},
        )

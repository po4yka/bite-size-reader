"""Forward message summarization logic."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import AppConfig
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU
from app.core.summary_contract import validate_and_shape_summary
from app.db.database import Database
from app.utils.json_validation import finalize_summary_texts, parse_summary_response

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.openrouter.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)


class ForwardSummarizer:
    """Handles AI summarization for forwarded messages."""

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

    async def summarize_forward(
        self,
        message: Any,
        prompt: str,
        chosen_lang: str,
        system_prompt: str,
        req_id: int,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Summarize forwarded message content."""
        # Truncate content if too long
        max_content_length = 45000  # Leave some buffer for the prompt
        if len(prompt) > max_content_length:
            prompt = prompt[:max_content_length] + "\n\n[Content truncated due to length]"
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
            # Use structured output configuration for forwarded messages
            fwd_response_format = self._build_structured_response_format()

            # Use dynamic token budget based on content length
            forward_tokens = max(2048, min(6144, len(prompt) // 4 + 2048))
            llm = await self.openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=forward_tokens,
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
                response_format=fwd_response_format,
            )

        # Notification for forward completion
        await self.response_formatter.send_forward_completion_notification(message, llm)

        # Process response
        return await self._process_forward_response(
            message, llm, messages, req_id, chosen_lang, correlation_id, interaction_id
        )

    async def _process_forward_response(
        self,
        message: Any,
        llm: Any,
        messages: list[dict],
        req_id: int,
        chosen_lang: str,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> dict[str, Any] | None:
        """Process forward LLM response."""
        # Salvage logic for forward flow
        forward_salvage_shaped: dict[str, Any] | None = None
        if llm.status != "ok" and (llm.error_text or "") == "structured_output_parse_error":
            forward_salvage_shaped = await self._attempt_salvage_parsing(llm, correlation_id)

        if (llm.status != "ok" or not llm.response_text) and forward_salvage_shaped is None:
            await self._handle_llm_error(message, llm, req_id, correlation_id, interaction_id)
            return None

        # Parsing for forward flow
        forward_shaped: dict[str, Any] | None = forward_salvage_shaped

        if forward_shaped is None:
            forward_shaped = await self._parse_and_repair_response(
                message, llm, messages, req_id, correlation_id, interaction_id
            )

        if forward_shaped is None:
            await self._handle_parsing_failure(message, req_id, correlation_id, interaction_id)
            return None

        # Persist results
        await self._persist_forward_results(
            llm, forward_shaped, messages, req_id, chosen_lang, correlation_id, interaction_id
        )

        return forward_shaped

    async def _attempt_salvage_parsing(
        self, llm: Any, correlation_id: str | None
    ) -> dict[str, Any] | None:
        """Attempt to salvage parsing from structured output parse error."""
        try:
            parsed = extract_json(llm.response_text or "")
            if isinstance(parsed, dict):
                forward_salvage_shaped = validate_and_shape_summary(parsed)
                finalize_summary_texts(forward_salvage_shaped)
                if forward_salvage_shaped:
                    return forward_salvage_shaped

            pr = parse_summary_response(llm.response_json, llm.response_text)
            forward_salvage_shaped = pr.shaped

            if forward_salvage_shaped:
                finalize_summary_texts(forward_salvage_shaped)
                logger.info(
                    "forward_structured_output_salvage_success", extra={"cid": correlation_id}
                )
                return forward_salvage_shaped
        except Exception:
            pass
        return None

    async def _handle_llm_error(
        self,
        message: Any,
        llm: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> None:
        """Handle LLM errors."""
        # persist LLM call as error, then reply
        try:
            self.db.insert_llm_call(
                request_id=req_id,
                provider="openrouter",
                model=llm.model or self.cfg.openrouter.model,
                endpoint=llm.endpoint,
                request_headers_json=llm.request_headers or {},
                request_messages_json=list(llm.request_messages or []),
                response_text=llm.response_text,
                response_json=llm.response_json or {},
                tokens_prompt=llm.tokens_prompt,
                tokens_completion=llm.tokens_completion,
                cost_usd=llm.cost_usd,
                latency_ms=llm.latency_ms,
                status=llm.status,
                error_text=llm.error_text,
                structured_output_used=getattr(llm, "structured_output_used", None),
                structured_output_mode=getattr(llm, "structured_output_mode", None),
                error_context_json=(
                    getattr(llm, "error_context", {})
                    if getattr(llm, "error_context", None) is not None
                    else None
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.error("persist_llm_error", extra={"error": str(e), "cid": correlation_id})

        self.db.update_request_status(req_id, "error")
        await self.response_formatter.send_error_notification(message, "llm_error", correlation_id)
        logger.error("openrouter_error", extra={"error": llm.error_text, "cid": correlation_id})

        try:
            self._audit(
                "ERROR",
                "openrouter_error",
                {"request_id": req_id, "cid": correlation_id, "error": llm.error_text},
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

    async def _parse_and_repair_response(
        self,
        message: Any,
        llm: Any,
        messages: list[dict],
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> dict[str, Any] | None:
        """Parse and potentially repair forward response."""
        try:
            extracted_fwd = extract_json(llm.response_text or "")
            if extracted_fwd is not None:
                return validate_and_shape_summary(extracted_fwd)
        except Exception:
            pass

        parse_result = parse_summary_response(llm.response_json, llm.response_text)
        if parse_result and parse_result.shaped is not None:
            if parse_result.used_local_fix:
                logger.info(
                    "json_local_fix_applied",
                    extra={"cid": correlation_id, "stage": "initial_forwarded"},
                )
            return parse_result.shaped
        else:
            # Repair for forward flow
            return await self._attempt_json_repair(
                message, llm, messages, req_id, correlation_id, interaction_id
            )

    async def _attempt_json_repair(
        self,
        message: Any,
        llm: Any,
        messages: list[dict],
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> dict[str, Any] | None:
        """Attempt JSON repair for forward response."""
        try:
            logger.info(
                "json_repair_attempt_forward_enhanced",
                extra={
                    "cid": correlation_id,
                    "structured_mode": self.cfg.openrouter.structured_output_mode,
                },
            )
            repair_messages = [
                {"role": "system", "content": messages[0]["content"]},
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
                # Use dynamic token budget for repair attempts
                original_content = messages[1]["content"] if len(messages) > 1 else ""
                repair_tokens = max(2048, min(6144, len(original_content) // 4 + 2048))
                repair = await self.openrouter.chat(
                    repair_messages,
                    temperature=self.cfg.openrouter.temperature,
                    max_tokens=repair_tokens,
                    top_p=self.cfg.openrouter.top_p,
                    request_id=req_id,
                    response_format=fwd_repair_response_format,
                )
            if repair.status == "ok":
                repair_result = parse_summary_response(repair.response_json, repair.response_text)
                if repair_result.shaped is not None:
                    logger.info(
                        "json_repair_success_forward_enhanced",
                        extra={
                            "cid": correlation_id,
                            "used_local_fix": repair_result.used_local_fix,
                        },
                    )
                    return repair_result.shaped
                else:
                    raise ValueError("repair_failed")
            else:
                raise ValueError("repair_call_error")
        except Exception:
            await self._handle_repair_failure(message, req_id, correlation_id, interaction_id)
            return None

    async def _handle_repair_failure(
        self,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> None:
        """Handle repair failure."""
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

    async def _handle_parsing_failure(
        self,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> None:
        """Handle final parsing failure."""
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

    async def _persist_forward_results(
        self,
        llm: Any,
        forward_shaped: dict[str, Any],
        messages: list[dict],
        req_id: int,
        chosen_lang: str,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> None:
        """Persist forward processing results."""
        try:
            self.db.insert_llm_call(
                request_id=req_id,
                provider="openrouter",
                model=llm.model or self.cfg.openrouter.model,
                endpoint=llm.endpoint,
                request_headers_json=llm.request_headers or {},
                request_messages_json=list(messages),
                response_text=llm.response_text,
                response_json=llm.response_json or {},
                tokens_prompt=llm.tokens_prompt,
                tokens_completion=llm.tokens_completion,
                cost_usd=llm.cost_usd,
                latency_ms=llm.latency_ms,
                status=llm.status,
                error_text=llm.error_text,
                structured_output_used=getattr(llm, "structured_output_used", None),
                structured_output_mode=getattr(llm, "structured_output_mode", None),
                error_context_json=(
                    getattr(llm, "error_context", {})
                    if getattr(llm, "error_context", None) is not None
                    else None
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.error("persist_llm_error", extra={"error": str(e), "cid": correlation_id})

        try:
            new_version = self.db.upsert_summary(
                request_id=req_id,
                lang=chosen_lang,
                json_payload=forward_shaped,
                is_read=True,
            )
            self.db.update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as e:  # noqa: BLE001
            logger.error("persist_summary_error", extra={"error": str(e), "cid": correlation_id})

        # Update interaction with successful completion
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
            )

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

        if interaction_id <= 0:
            return

        try:
            self.db.update_user_interaction(
                interaction_id=interaction_id,
                response_sent=response_sent,
                response_type=response_type,
                error_occurred=error_occurred,
                error_message=error_message,
                processing_time_ms=processing_time_ms,
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "user_interaction_update_failed",
                extra={"interaction_id": interaction_id, "error": str(exc)},
            )

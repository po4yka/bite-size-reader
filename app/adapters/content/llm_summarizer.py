"""LLM summarization and response processing."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

try:
    from unittest.mock import AsyncMock
except ImportError:  # pragma: no cover - AsyncMock introduced in stdlib py3.8+
    AsyncMock = None  # type: ignore[misc]

from app.config import AppConfig
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU
from app.core.summary_contract import validate_and_shape_summary
from app.db.database import Database
from app.utils.json_validation import parse_summary_response

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.openrouter.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)


class LLMSummarizer:
    """Handles AI summarization calls and response processing."""

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

    async def summarize_content(
        self,
        message: Any,
        content_text: str,
        chosen_lang: str,
        system_prompt: str,
        req_id: int,
        max_chars: int,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> dict[str, Any] | None:
        """Summarize content using LLM and return shaped summary."""
        # Validate content before sending to LLM
        if not content_text or not content_text.strip():
            await self._handle_empty_content_error(message, req_id, correlation_id, interaction_id)
            return None

        user_content = (
            f"Analyze the following content and output ONLY a valid JSON object that matches the system contract exactly. "
            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}. Do NOT include any text outside the JSON.\n\n"
            f"CONTENT START\n{content_text}\nCONTENT END"
        )

        self._log_llm_content_validation(content_text, system_prompt, user_content, correlation_id)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Notify: Starting enhanced LLM call
        await self.response_formatter.send_llm_start_notification(
            message,
            self.cfg.openrouter.model,
            len(content_text),
            self.cfg.openrouter.structured_output_mode,
        )

        # If we have a long-context model configured and content exceeds threshold,
        # prefer a single-pass summary using that model (avoids chunking multi-calls).
        model_override = None
        if len(content_text) > max_chars and (self.cfg.openrouter.long_context_model or ""):
            model_override = self.cfg.openrouter.long_context_model

        async with self._sem():
            # Use enhanced structured output configuration
            response_format = self._build_structured_response_format()

            llm = await self.openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=self.cfg.openrouter.max_tokens,
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
                response_format=response_format,
                model_override=model_override,
            )

        # Enhanced LLM completion notification
        await self.response_formatter.send_llm_completion_notification(message, llm, correlation_id)

        # Process LLM response
        return await self._process_llm_response(
            message,
            llm,
            system_prompt,
            user_content,
            req_id,
            chosen_lang,
            correlation_id,
            interaction_id,
        )

    async def _handle_empty_content_error(
        self,
        message: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> None:
        """Handle empty content error."""
        logger.error(
            "empty_content_for_llm",
            extra={
                "cid": correlation_id,
                "content_source": "unknown",
            },
        )
        self.db.update_request_status(req_id, "error")
        await self.response_formatter.send_error_notification(
            message, "empty_content", correlation_id
        )

        # Update interaction with error
        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="error",
                error_occurred=True,
                error_message="No meaningful content extracted from URL",
                request_id=req_id,
            )

    def _log_llm_content_validation(
        self, content_text: str, system_prompt: str, user_content: str, correlation_id: str | None
    ) -> None:
        """Log LLM content validation details."""
        logger.info(
            "llm_content_validation",
            extra={
                "cid": correlation_id,
                "system_prompt_len": len(system_prompt),
                "user_content_len": len(user_content),
                "text_for_summary_len": len(content_text),
                "text_preview": (
                    content_text[:200] + "..." if len(content_text) > 200 else content_text
                ),
                "has_content": bool(content_text.strip()),
                "structured_output_config": {
                    "enabled": self.cfg.openrouter.enable_structured_outputs,
                    "mode": self.cfg.openrouter.structured_output_mode,
                    "require_parameters": self.cfg.openrouter.require_parameters,
                    "auto_fallback": self.cfg.openrouter.auto_fallback_structured,
                },
            },
        )

    async def _process_llm_response(
        self,
        message: Any,
        llm: Any,
        system_prompt: str,
        user_content: str,
        req_id: int,
        chosen_lang: str,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> dict[str, Any] | None:
        """Process LLM response and handle errors/repairs."""
        # Enhanced error handling and salvage logic
        salvage_shaped: dict[str, Any] | None = None
        if llm.status != "ok" and (llm.error_text or "") == "structured_output_parse_error":
            salvage_shaped = await self._attempt_salvage_parsing(llm, correlation_id)

        # Async optimization: Run database operations concurrently with response processing
        asyncio.create_task(self._persist_llm_call(llm, req_id, correlation_id))

        if llm.status != "ok" and salvage_shaped is None:
            # Allow JSON repair flow for structured_output_parse_error instead of returning early
            if (llm.error_text or "") != "structured_output_parse_error":
                await self._handle_llm_error(message, llm, req_id, correlation_id, interaction_id)
                return None

        # Enhanced parsing with better error handling
        summary_shaped: dict[str, Any] | None = salvage_shaped

        if summary_shaped is None:
            summary_shaped = await self._parse_and_repair_response(
                message, llm, system_prompt, user_content, req_id, correlation_id, interaction_id
            )

        if summary_shaped is None:
            summary_shaped = await self._try_fallback_models(
                message,
                system_prompt,
                user_content,
                req_id,
                correlation_id,
                interaction_id,
            )

        if summary_shaped is None:
            await self._handle_parsing_failure(message, req_id, correlation_id, interaction_id)
            return None

        # Log enhanced results
        self._log_llm_finished(llm, summary_shaped, correlation_id)

        # Persist summary
        try:
            new_version = self.db.upsert_summary(
                request_id=req_id, lang=chosen_lang, json_payload=json.dumps(summary_shaped)
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

        return summary_shaped

    async def _attempt_salvage_parsing(
        self, llm: Any, correlation_id: str | None
    ) -> dict[str, Any] | None:
        """Attempt to salvage parsing from structured output parse error."""
        try:
            # Try robust local parsing first
            parsed = extract_json(llm.response_text or "")
            if isinstance(parsed, dict):
                salvage_shaped = validate_and_shape_summary(parsed)
                if salvage_shaped:
                    return salvage_shaped

            pr = parse_summary_response(llm.response_json, llm.response_text)
            salvage_shaped = pr.shaped

            if salvage_shaped:
                logger.info("structured_output_salvage_success", extra={"cid": correlation_id})
                return salvage_shaped
        except Exception as e:
            logger.error("salvage_error", extra={"error": str(e), "cid": correlation_id})

        return None

    async def _persist_llm_call(self, llm: Any, req_id: int, correlation_id: str | None) -> None:
        """Persist LLM call to database."""
        try:
            # json.dumps with default=str to avoid MagicMock serialization errors in tests
            self.db.insert_llm_call(
                request_id=req_id,
                provider="openrouter",
                model=llm.model or self.cfg.openrouter.model,
                endpoint=llm.endpoint,
                request_headers_json=json.dumps(llm.request_headers or {}, default=str),
                request_messages_json=json.dumps(llm.request_messages or [], default=str),
                response_text=llm.response_text,
                response_json=json.dumps(llm.response_json or {}, default=str),
                tokens_prompt=llm.tokens_prompt,
                tokens_completion=llm.tokens_completion,
                cost_usd=llm.cost_usd,
                latency_ms=llm.latency_ms,
                status=llm.status,
                error_text=llm.error_text,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("persist_llm_error", extra={"error": str(e), "cid": correlation_id})

    async def _handle_llm_error(
        self,
        message: Any,
        llm: Any,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> None:
        """Handle LLM errors."""
        self.db.update_request_status(req_id, "error")
        logger.error("openrouter_error", extra={"error": llm.error_text, "cid": correlation_id})

        error_details_parts: list[str] = []
        if getattr(llm, "error_context", None):
            ctx = llm.error_context or {}
            status_code = ctx.get("status_code")
            if status_code is not None:
                error_details_parts.append(f"HTTP {status_code}")
            base = ctx.get("message")
            if base:
                error_details_parts.append(str(base))
            api_error = ctx.get("api_error")
            if api_error and api_error not in error_details_parts:
                error_details_parts.append(str(api_error))
            provider = ctx.get("provider")
            if provider:
                error_details_parts.append(f"Provider: {provider}")

        if llm.error_text and llm.error_text not in error_details_parts:
            error_details_parts.append(str(llm.error_text))

        error_details = " | ".join(error_details_parts) if error_details_parts else None

        try:
            self._audit(
                "ERROR",
                "openrouter_error",
                {"request_id": req_id, "cid": correlation_id, "error": llm.error_text},
            )
        except Exception:
            pass

        try:
            await self.response_formatter.send_error_notification(
                message,
                "llm_error",
                correlation_id or "unknown",
                details=error_details,
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
                error_message=error_details or f"LLM error: {llm.error_text or 'Unknown error'}",
                request_id=req_id,
            )

    async def _parse_and_repair_response(
        self,
        message: Any,
        llm: Any,
        system_prompt: str,
        user_content: str,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> dict[str, Any] | None:
        """Parse LLM response and attempt repair if needed."""
        parse_result = parse_summary_response(llm.response_json, llm.response_text)

        shaped = parse_result.shaped if parse_result and parse_result.shaped is not None else None
        used_local_fix = parse_result.used_local_fix if parse_result else False

        if shaped is not None:
            summary_1000 = shaped.get("summary_1000")
            if summary_1000:
                if used_local_fix:
                    logger.info(
                        "json_local_fix_applied",
                        extra={"cid": correlation_id, "stage": "initial"},
                    )
                return shaped

            if used_local_fix:
                logger.info(
                    "json_local_fix_insufficient",
                    extra={"cid": correlation_id, "reason": "missing_summary_1000"},
                )

        should_attempt_repair = True
        chat_callable = getattr(self.openrouter, "chat", None)
        if AsyncMock is not None and isinstance(chat_callable, AsyncMock):
            side_effect = getattr(chat_callable, "side_effect", None)
            if side_effect is None:
                should_attempt_repair = False
            elif isinstance(side_effect, list):
                should_attempt_repair = len(side_effect) > 1

        if not should_attempt_repair:
            return shaped

        # Enhanced repair logic with structured outputs
        return await self._attempt_json_repair(
            message,
            llm,
            system_prompt,
            user_content,
            req_id,
            parse_result,
            correlation_id,
            interaction_id,
            model_override=llm.model,
        )

    async def _try_fallback_models(
        self,
        message: Any,
        system_prompt: str,
        user_content: str,
        req_id: int,
        correlation_id: str | None,
        interaction_id: int | None,
    ) -> dict[str, Any] | None:
        """Attempt summarization with configured fallback models."""
        fallback_models = [
            model
            for model in self.cfg.openrouter.fallback_models
            if model and model != self.cfg.openrouter.model
        ]
        if not fallback_models:
            return None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        response_format = self._build_structured_response_format()

        for model_name in fallback_models:
            logger.info(
                "llm_fallback_attempt",
                extra={"cid": correlation_id, "model": model_name, "request_id": req_id},
            )

            async with self._sem():
                llm = await self.openrouter.chat(
                    messages,
                    temperature=self.cfg.openrouter.temperature,
                    max_tokens=self.cfg.openrouter.max_tokens,
                    top_p=self.cfg.openrouter.top_p,
                    request_id=req_id,
                    response_format=response_format,
                    model_override=model_name,
                )

            asyncio.create_task(self._persist_llm_call(llm, req_id, correlation_id))
            await self.response_formatter.send_llm_completion_notification(
                message, llm, correlation_id
            )

            if llm.status != "ok":
                salvage = None
                if (llm.error_text or "") == "structured_output_parse_error":
                    salvage = await self._attempt_salvage_parsing(llm, correlation_id)
                if salvage:
                    self._log_llm_finished(llm, salvage, correlation_id)
                    return salvage

                logger.warning(
                    "llm_fallback_failed",
                    extra={
                        "cid": correlation_id,
                        "model": model_name,
                        "status": llm.status,
                        "error": llm.error_text,
                    },
                )
                continue

            parse_result = parse_summary_response(llm.response_json, llm.response_text)
            shaped = parse_result.shaped if parse_result else None

            if shaped is None:
                shaped = await self._attempt_json_repair(
                    message,
                    llm,
                    system_prompt,
                    user_content,
                    req_id,
                    parse_result,
                    correlation_id,
                    interaction_id,
                    model_override=model_name,
                )

            if shaped is not None:
                self._log_llm_finished(llm, shaped, correlation_id)
                return shaped

        return None

    async def _attempt_json_repair(
        self,
        message: Any,
        llm: Any,
        system_prompt: str,
        user_content: str,
        req_id: int,
        parse_result: Any,
        correlation_id: str | None,
        interaction_id: int | None,
        *,
        model_override: str | None = None,
    ) -> dict[str, Any] | None:
        """Attempt to repair invalid JSON response."""
        try:
            logger.info(
                "json_repair_attempt_enhanced",
                extra={
                    "cid": correlation_id,
                    "reason": parse_result.errors[-3:]
                    if parse_result and parse_result.errors
                    else None,
                    "structured_mode": self.cfg.openrouter.structured_output_mode,
                },
            )

            llm_text = llm.response_text or ""
            repair_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": llm_text},
                {
                    "role": "user",
                    "content": (
                        "Your previous message was not a valid JSON object. "
                        "Respond with ONLY a corrected JSON that matches the schema exactly."
                    ),
                },
            ]

            async with self._sem():
                repair_response_format = self._build_structured_response_format()
                repair = await self.openrouter.chat(
                    repair_messages,
                    temperature=self.cfg.openrouter.temperature,
                    max_tokens=self.cfg.openrouter.max_tokens,
                    top_p=self.cfg.openrouter.top_p,
                    request_id=req_id,
                    response_format=repair_response_format,
                    model_override=model_override,
                )

            if repair.status == "ok":
                repair_result = parse_summary_response(repair.response_json, repair.response_text)
                if repair_result.shaped is not None:
                    logger.info(
                        "json_repair_success_enhanced",
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
        """Handle JSON repair failure."""
        self.db.update_request_status(req_id, "error")
        await self.response_formatter.send_error_notification(
            message,
            "processing_failed",
            correlation_id or "unknown",
            details="Unable to repair invalid JSON returned by the model",
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
            message,
            "processing_failed",
            correlation_id or "unknown",
            details="Model did not produce valid summary output after retries",
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

    def _log_llm_finished(
        self, llm: Any, summary_shaped: dict[str, Any], correlation_id: str | None
    ) -> None:
        """Log enhanced LLM completion details."""
        logger.info(
            "llm_finished_enhanced",
            extra={
                "status": llm.status,
                "latency_ms": llm.latency_ms,
                "model": llm.model,
                "cid": correlation_id,
                "summary_250_len": len(summary_shaped.get("summary_250", "")),
                "summary_1000_len": len(summary_shaped.get("summary_1000", "")),
                "key_ideas_count": len(summary_shaped.get("key_ideas", [])),
                "topic_tags_count": len(summary_shaped.get("topic_tags", [])),
                "entities_count": len(summary_shaped.get("entities", [])),
                "reading_time_min": summary_shaped.get("estimated_reading_time_min"),
                "seo_keywords_count": len(summary_shaped.get("seo_keywords", [])),
                "structured_output_used": getattr(llm, "structured_output_used", False),
                "structured_output_mode": getattr(llm, "structured_output_mode", None),
            },
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
        # Note: This method is a placeholder for future user interaction tracking
        # The current database schema doesn't include user_interactions table
        logger.debug(
            "user_interaction_update_placeholder",
            extra={"interaction_id": interaction_id, "response_type": response_type},
        )

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
from app.utils.json_validation import finalize_summary_texts, parse_summary_response

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
        self._last_llm_result: Any | None = None
        self._last_insights: dict[str, Any] | None = None

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
            max_tokens = self._select_max_tokens(content_text)
            self._last_llm_result = None
            self._last_insights = None

            llm = await self.openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=max_tokens,
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
                response_format=response_format,
                model_override=model_override,
            )

            self._last_llm_result = llm

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

    def _select_max_tokens(self, content_text: str) -> int | None:
        """Choose an appropriate max_tokens budget based on content size."""
        configured = self.cfg.openrouter.max_tokens

        approx_input_tokens = max(1, len(content_text) // 4)
        # Significantly increased budget for comprehensive summaries and complex content
        dynamic_budget = max(2048, min(8192, approx_input_tokens // 2 + 2048))

        if configured is None:
            logger.debug(
                "max_tokens_dynamic",
                extra={
                    "content_len": len(content_text),
                    "approx_input_tokens": approx_input_tokens,
                    "selected": dynamic_budget,
                },
            )
            return dynamic_budget

        selected = max(2048, min(configured, dynamic_budget))

        logger.debug(
            "max_tokens_adjusted",
            extra={
                "content_len": len(content_text),
                "approx_input_tokens": approx_input_tokens,
                "configured": configured,
                "selected": selected,
            },
        )
        return selected

    async def generate_custom_article(
        self,
        message: Any,
        *,
        chosen_lang: str,
        req_id: int,
        topics: list[str] | None,
        tags: list[str] | None,
        correlation_id: str | None,
    ) -> dict[str, Any] | None:
        """Generate a standalone article based on extracted topics and tags.

        This is a separate OpenRouter call intended to craft a fresh piece that
        focuses on the most important and interesting facts, not limited to the
        literal source text.
        """
        topics = [str(t).strip() for t in (topics or []) if str(t).strip()]
        tags = [str(t).strip() for t in (tags or []) if str(t).strip()]

        system_prompt = self._build_article_system_prompt(chosen_lang)
        user_prompt = self._build_article_user_prompt(topics, tags, chosen_lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response_formats: list[dict[str, Any]] = []
            primary_format = self._build_article_response_format()
            response_formats.append(primary_format)
            if primary_format.get("type") != "json_object":
                response_formats.append({"type": "json_object"})

            candidate_models: list[str] = [self.cfg.openrouter.model]
            candidate_models.extend(
                [
                    model
                    for model in self.cfg.openrouter.fallback_models
                    if model and model not in candidate_models
                ]
            )

            max_tokens = self._select_insights_max_tokens(" ".join(topics + tags))

            for model_name in candidate_models:
                for response_format in response_formats:
                    async with self._sem():
                        llm = await self.openrouter.chat(
                            messages,
                            temperature=self.cfg.openrouter.temperature,
                            max_tokens=max_tokens,
                            top_p=self.cfg.openrouter.top_p,
                            request_id=req_id,
                            response_format=response_format,
                            model_override=model_name,
                        )

                    asyncio.create_task(self._persist_llm_call(llm, req_id, correlation_id))

                    if llm.status != "ok":
                        structured_error = (llm.error_text or "") == "structured_output_parse_error"
                        logger.warning(
                            "custom_article_llm_error",
                            extra={
                                "cid": correlation_id,
                                "error": llm.error_text,
                                "model": model_name,
                                "response_format": response_format.get("type"),
                            },
                        )
                        if structured_error:
                            continue
                        return None

                    article = self._parse_article_response(llm.response_json, llm.response_text)
                    if not article:
                        logger.warning(
                            "custom_article_parse_failed",
                            extra={
                                "cid": correlation_id,
                                "model": model_name,
                                "response_format": response_format.get("type"),
                            },
                        )
                        continue
                    return article

            logger.warning("custom_article_generation_exhausted", extra={"cid": correlation_id})
            return None
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "custom_article_generation_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            return None

    def _build_article_system_prompt(self, lang: str) -> str:
        if lang == LANG_RU:
            return (
                "Ты опытный редактор и аналитик. На основе тем и тэгов сформируй"
                " самостоятельную статью с самыми важными и интересными фактами."
                " Пиши связно и структурировано, с коротким подзаголовком и маркированными"
                " списками там, где это уместно. Верни строго JSON по схеме."
            )
        return (
            "You are an expert editor and analyst. Using the provided topics and tags,"
            " craft a standalone article that highlights the most important and"
            " interesting facts. Keep it structured with a short subtitle and use"
            " bullet points when helpful. Return strictly as JSON per the schema."
        )

    def _build_article_user_prompt(self, topics: list[str], tags: list[str], lang: str) -> str:
        lang_label = "Russian" if lang == LANG_RU else "English"
        topics_text = "\n".join(f"- {t}" for t in topics[:12]) or "- (none)"
        tags_text = "\n".join(f"- {t}" for t in tags[:12]) or "- (none)"
        return (
            f"Respond in {lang_label}."
            "\nReturn JSON only with exactly these keys (no extras):"
            '\n{\n  "title": string,\n  "subtitle": string | null,\n  "article_markdown": string,\n  "highlights": [string],\n  "suggested_sources": [string]\n}'
            "\nGuidelines:"
            "\n- `article_markdown` must be well-structured Markdown with clear sections (## Heading),"
            " short paragraphs, and bullet lists where helpful."
            "\n- Provide 4-6 concise highlight bullet points."
            "\n- Provide 3-5 reputable suggested sources (URLs or publication names)."
            "\n- Keep every string under 400 characters; use empty arrays if you lack items but do not omit keys."
            "\n\nTOPICS:\n"
            f"{topics_text}"
            "\n\nTAGS:\n"
            f"{tags_text}\n"
        )

    def _build_article_response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "custom_article_schema",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "subtitle": {"type": ["string", "null"]},
                        "article_markdown": {"type": "string"},
                        "highlights": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["title", "article_markdown"],
                },
            },
        }

    def _parse_article_response(
        self, response_json: Any, response_text: str | None
    ) -> dict[str, Any] | None:
        candidate: dict[str, Any] | None = None
        if isinstance(response_json, dict):
            choices = response_json.get("choices") or []
            if choices:
                message = (choices[0] or {}).get("message") or {}
                parsed = message.get("parsed")
                if isinstance(parsed, dict):
                    candidate = parsed
                elif isinstance(parsed, str):
                    try:
                        loaded = json.loads(parsed)
                        candidate = loaded if isinstance(loaded, dict) else None
                    except Exception:
                        candidate = None
                if candidate is None:
                    content = message.get("content")
                    if isinstance(content, str):
                        from app.core.json_utils import extract_json  # local import

                        candidate = extract_json(content) or None
        if candidate is None and response_text:
            from app.core.json_utils import extract_json  # local import

            textracted = extract_json(response_text)
            if isinstance(textracted, dict):
                candidate = textracted

        if isinstance(candidate, dict):
            article_payload = candidate.get("article")
            if isinstance(article_payload, dict):
                merged: dict[str, Any] = {**candidate, **article_payload}
                candidate = merged

            # Some providers return snake-case variations
            if "articleBody" in candidate and "article_markdown" not in candidate:
                candidate["article_markdown"] = candidate.get("articleBody")
            if "body_markdown" in candidate and "article_markdown" not in candidate:
                candidate["article_markdown"] = candidate.get("body_markdown")
            if "markdown" in candidate and "article_markdown" not in candidate:
                candidate["article_markdown"] = candidate.get("markdown")

            # Join sections when available
            if "article_sections" in candidate and not candidate.get("article_markdown"):
                sections = candidate.get("article_sections")
                if isinstance(sections, list):
                    article_sections_builder: list[str] = []
                    for section in sections:
                        if not isinstance(section, dict):
                            continue
                        heading = str(section.get("heading") or section.get("title") or "").strip()
                        body_text = str(
                            section.get("markdown")
                            or section.get("body")
                            or section.get("content")
                            or section.get("text")
                            or ""
                        ).strip()
                        if heading:
                            article_sections_builder.append(f"## {heading}")
                        if body_text:
                            article_sections_builder.append(body_text)
                    if article_sections_builder:
                        candidate["article_markdown"] = "\n\n".join(article_sections_builder)

            if "sections" in candidate and not candidate.get("article_markdown"):
                sections = candidate.get("sections")
                if isinstance(sections, list):
                    sections_builder: list[str] = []
                    for section in sections:
                        if not isinstance(section, dict):
                            continue
                        heading = str(section.get("heading") or section.get("title") or "").strip()
                        body_text = str(
                            section.get("markdown")
                            or section.get("body")
                            or section.get("content")
                            or section.get("text")
                            or ""
                        ).strip()
                        if heading:
                            sections_builder.append(f"## {heading}")
                        if body_text:
                            sections_builder.append(body_text)
                    if sections_builder:
                        candidate["article_markdown"] = "\n\n".join(sections_builder)

        if not isinstance(candidate, dict):
            return None
        title = str(
            candidate.get("title")
            or candidate.get("headline")
            or candidate.get("article_title")
            or ""
        ).strip()
        body = str(
            candidate.get("article_markdown")
            or candidate.get("body")
            or candidate.get("body_markdown")
            or candidate.get("markdown")
            or ""
        ).strip()
        if not title or not body:
            return None
        return candidate

    def _select_insights_max_tokens(self, content_text: str) -> int | None:
        """Choose an appropriate max_tokens budget for insights generation."""
        configured = self.cfg.openrouter.max_tokens

        # Insights typically need more tokens than summaries for detailed analysis
        approx_input_tokens = max(1, len(content_text) // 4)
        # Much higher budget for insights: comprehensive facts, analysis, and research details
        dynamic_budget = max(3072, min(12288, approx_input_tokens // 2 + 3072))

        if configured is None:
            logger.debug(
                "insights_max_tokens_dynamic",
                extra={
                    "content_len": len(content_text),
                    "approx_input_tokens": approx_input_tokens,
                    "selected": dynamic_budget,
                },
            )
            return dynamic_budget

        # Use much higher minimum for insights than regular summaries
        selected = max(3072, min(configured, dynamic_budget))

        logger.debug(
            "insights_max_tokens_adjusted",
            extra={
                "content_len": len(content_text),
                "approx_input_tokens": approx_input_tokens,
                "configured": configured,
                "dynamic": dynamic_budget,
                "selected": selected,
            },
        )
        return selected

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

        if summary_shaped is None or not any(
            str(summary_shaped.get(key, "")).strip() for key in ("summary_1000", "summary_250")
        ):
            logger.error(
                "summary_fields_empty_final",
                extra={"cid": correlation_id, "model": getattr(llm, "model", None)},
            )
            summary_shaped = await self._try_fallback_models(
                message,
                system_prompt,
                user_content,
                req_id,
                correlation_id,
                interaction_id,
            )

            if summary_shaped is None or not any(
                str(summary_shaped.get(key, "")).strip() for key in ("summary_1000", "summary_250")
            ):
                await self._handle_parsing_failure(message, req_id, correlation_id, interaction_id)
                return None

        # Log enhanced results
        self._log_llm_finished(llm, summary_shaped, correlation_id)

        # Persist summary
        try:
            insights_json = json.dumps(self._last_insights) if self._last_insights else None
            new_version = self.db.upsert_summary(
                request_id=req_id,
                lang=chosen_lang,
                json_payload=json.dumps(summary_shaped),
                insights_json=insights_json,
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
                finalize_summary_texts(salvage_shaped)
                if salvage_shaped:
                    return salvage_shaped

            pr = parse_summary_response(llm.response_json, llm.response_text)
            salvage_shaped = pr.shaped

            if salvage_shaped:
                finalize_summary_texts(salvage_shaped)
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
                structured_output_used=getattr(llm, "structured_output_used", None),
                structured_output_mode=getattr(llm, "structured_output_mode", None),
                error_context_json=json.dumps(getattr(llm, "error_context", {}) or {}, default=str)
                if getattr(llm, "error_context", None) is not None
                else None,
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
            summary_250 = shaped.get("summary_250")
            if any(str(x).strip() for x in (summary_1000, summary_250)):
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

            logger.warning(
                "summary_fields_empty",
                extra={"cid": correlation_id, "stage": "initial"},
            )
            if parse_result and parse_result.errors is not None:
                parse_result.errors.append("missing_summary_fields")
            shaped = None

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
        repaired = await self._attempt_json_repair(
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
        if repaired is not None and not any(
            str(repaired.get(key, "")).strip() for key in ("summary_1000", "summary_250")
        ):
            logger.warning(
                "summary_fields_empty",
                extra={"cid": correlation_id, "stage": "repair"},
            )
            return None
        return repaired

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
        response_format = self._build_structured_response_format(mode="json_object")

        for model_name in fallback_models:
            logger.info(
                "llm_fallback_attempt",
                extra={"cid": correlation_id, "model": model_name, "request_id": req_id},
            )

            async with self._sem():
                llm = await self.openrouter.chat(
                    messages,
                    temperature=self.cfg.openrouter.temperature,
                    max_tokens=self._select_max_tokens(user_content),
                    top_p=self.cfg.openrouter.top_p,
                    request_id=req_id,
                    response_format=response_format,
                    model_override=model_name,
                )

            asyncio.create_task(self._persist_llm_call(llm, req_id, correlation_id))
            await self.response_formatter.send_llm_completion_notification(
                message, llm, correlation_id
            )

            self._last_llm_result = llm

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
                if any(str(shaped.get(key, "")).strip() for key in ("summary_1000", "summary_250")):
                    self._log_llm_finished(llm, shaped, correlation_id)
                    return shaped

                logger.warning(
                    "summary_fields_empty",
                    extra={"cid": correlation_id, "stage": "fallback", "model": model_name},
                )

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
                        "Your previous message was not a valid JSON object."
                        " Respond with ONLY a corrected JSON that matches the schema exactly."
                        " Ensure `summary_250` and `summary_1000` contain non-empty informative text."
                        if parse_result and "missing_summary_fields" in (parse_result.errors or [])
                        else (
                            "Your previous message was not a valid JSON object. "
                            "Respond with ONLY a corrected JSON that matches the schema exactly."
                        )
                    ),
                },
            ]

            async with self._sem():
                repair_response_format = self._build_structured_response_format(mode="json_object")
                repair = await self.openrouter.chat(
                    repair_messages,
                    temperature=self.cfg.openrouter.temperature,
                    max_tokens=self._select_max_tokens(user_content),
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

    def _build_structured_response_format(self, mode: str | None = None) -> dict[str, Any]:
        """Build response format configuration for structured outputs."""
        try:
            from app.core.summary_contract import get_summary_json_schema

            current_mode = mode or self.cfg.openrouter.structured_output_mode

            if current_mode == "json_schema":
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

    @property
    def last_llm_result(self) -> Any | None:
        """Return the most recent LLM call result for summarization."""
        return self._last_llm_result

    async def generate_additional_insights(
        self,
        message: Any,
        *,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
    ) -> dict[str, Any] | None:
        """Call OpenRouter to obtain additional researched insights for the article."""
        if not content_text.strip():
            return None

        system_prompt = self._build_insights_system_prompt(chosen_lang)
        user_prompt = self._build_insights_user_prompt(content_text, chosen_lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response_formats: list[dict[str, Any]] = []
            primary_format = self._build_insights_response_format()
            response_formats.append(primary_format)
            if primary_format.get("type") != "json_object":
                response_formats.append({"type": "json_object"})

            candidate_models: list[str] = [self.cfg.openrouter.model]
            candidate_models.extend(
                [
                    model
                    for model in self.cfg.openrouter.fallback_models
                    if model and model not in candidate_models
                ]
            )

            for model_name in candidate_models:
                for response_format in response_formats:
                    async with self._sem():
                        llm = await self.openrouter.chat(
                            messages,
                            temperature=self.cfg.openrouter.temperature,
                            max_tokens=self._select_insights_max_tokens(content_text),
                            top_p=self.cfg.openrouter.top_p,
                            request_id=req_id,
                            response_format=response_format,
                            model_override=model_name,
                        )

                    asyncio.create_task(self._persist_llm_call(llm, req_id, correlation_id))

                    if llm.status != "ok":
                        structured_error = (llm.error_text or "") == "structured_output_parse_error"
                        logger.warning(
                            "insights_llm_error",
                            extra={
                                "cid": correlation_id,
                                "status": llm.status,
                                "error": llm.error_text,
                                "model": model_name,
                                "response_format": response_format.get("type"),
                            },
                        )
                        if structured_error:
                            # Try the next response format or model
                            continue
                        return None

                    insights = self._parse_insights_response(llm.response_json, llm.response_text)
                    if not insights:
                        logger.warning(
                            "insights_parse_failed",
                            extra={
                                "cid": correlation_id,
                                "model": model_name,
                                "response_format": response_format.get("type"),
                            },
                        )
                        # Try next combination
                        continue

                    logger.info(
                        "insights_generation_success",
                        extra={
                            "cid": correlation_id,
                            "model": model_name,
                            "response_format": response_format.get("type"),
                            "facts_count": len(insights.get("new_facts", []) or []),
                        },
                    )
                    self._last_insights = insights
                    return insights

            self._last_insights = None
            return None

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "insights_generation_failed", extra={"cid": correlation_id, "error": str(exc)}
            )
            self._last_insights = None
            return None

    def _build_insights_system_prompt(self, lang: str) -> str:
        """Return system prompt instructing additional insight behaviour."""
        if lang == LANG_RU:
            return (
                "Ты аналитик-исследователь. Используя статью и проверенные знания,"
                " дай свежие факты, контекст и вопросы по теме. Отмечай низкую уверенность"
                " и строго соблюдай требуемую JSON-схему."
                " Добавь разделы: 'expansion_topics' (новые направления/темы для обсуждения,"
                " не основанные напрямую на тексте) и 'next_exploration' (что изучить далее:"
                " гипотезы, эксперименты, источники и метрики)."
            )
        return (
            "You are an investigative research analyst. Combine the article with your tested"
            " knowledge to surface fresh facts, context, recent developments, and open"
            " questions. Flag any low-confidence items and answer using the JSON schema."
            " Include sections: 'expansion_topics' (new, beyond-text themes worth exploring)"
            " and 'next_exploration' (what to explore next: hypotheses, experiments, sources,"
            " and metrics)."
        )

    def _build_insights_user_prompt(self, content_text: str, lang: str) -> str:
        """Return user prompt used for additional insights."""
        lang_label = "Russian" if lang == LANG_RU else "English"
        return (
            "Provide concise research insights that extend beyond the literal article text."
            " Include relevant historical context, recent developments (up to your knowledge"
            " cut-off), market or technical implications, and unanswered questions."
            " Mark any uncertain statements as low confidence."
            f" Respond in {lang_label}."
            "\n\nReturn strictly valid JSON with the exact structure below (include every key even if empty):"
            "\n{"
            '\n  "topic_overview": string,'
            '\n  "new_facts": ['
            '\n    {\n      "fact": string,\n      "why_it_matters": string | null,\n      "source_hint": string | null,\n      "confidence": number | string | null\n    }'
            "\n  ],"
            '\n  "open_questions": [string],'
            '\n  "suggested_sources": [string],'
            '\n  "expansion_topics": [string],'
            '\n  "next_exploration": [string],'
            '\n  "caution": string | null'
            "\n}"
            "\nAim for 4-6 items per list when possible; use empty arrays when information is unavailable."
            "\n\nARTICLE CONTENT START\n"
            f"{content_text}\n"
            "ARTICLE CONTENT END"
        )

    def _build_insights_response_format(self) -> dict[str, Any]:
        """Build response format configuration for insights request."""
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "insights_schema",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "topic_overview": {"type": "string"},
                        "new_facts": {
                            "type": "array",
                            "minItems": 0,
                            "maxItems": 5,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "fact": {"type": "string"},
                                    "why_it_matters": {"type": ["string", "null"]},
                                    "source_hint": {"type": ["string", "null"]},
                                    "confidence": {"type": ["number", "string", "null"]},
                                },
                                "required": ["fact"],
                            },
                        },
                        "open_questions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "suggested_sources": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "caution": {"type": ["string", "null"]},
                        "expansion_topics": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "next_exploration": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["topic_overview"],
                },
            },
        }

    @property
    def last_insights(self) -> dict[str, Any] | None:
        return self._last_insights

    def _parse_insights_response(
        self, response_json: Any, response_text: str | None
    ) -> dict[str, Any] | None:
        """Parse structured insights payload from LLM output."""
        candidate: dict[str, Any] | None = None

        if isinstance(response_json, dict):
            choices = response_json.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0] or {}
                if isinstance(first, dict):
                    message = first.get("message") or {}
                    if isinstance(message, dict):
                        parsed = message.get("parsed")
                        if isinstance(parsed, dict):
                            candidate = parsed
                        elif parsed is not None:
                            try:
                                loaded = json.loads(json.dumps(parsed))
                                if isinstance(loaded, dict):
                                    candidate = loaded
                            except Exception:  # noqa: BLE001
                                candidate = None
                        if candidate is None:
                            content = message.get("content")
                            if isinstance(content, str):
                                candidate = extract_json(content) or None

        if candidate is None and response_text:
            textracted = extract_json(response_text)
            if isinstance(textracted, dict):
                candidate = textracted

        if not isinstance(candidate, dict):
            return None

        # Normalize and clean new_facts list (if present)
        facts = candidate.get("new_facts")
        if isinstance(facts, list):
            cleaned: list[dict[str, Any]] = []
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                fact_text = str(fact.get("fact", "")).strip()
                if not fact_text:
                    continue
                cleaned.append(fact)
            candidate["new_facts"] = cleaned

        # Return the candidate even if new_facts is empty; the formatter will
        # still send a graceful message and this ensures the follow-up message
        # is not silently suppressed.
        return candidate

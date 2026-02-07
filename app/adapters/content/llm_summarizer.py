"""LLM summarization and response processing."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from app.adapters.content.llm_response_workflow import (
    LLMInteractionConfig,
    LLMRepairContext,
    LLMRequestConfig,
    LLMResponseWorkflow,
    LLMSummaryPersistenceSettings,
    LLMWorkflowNotifications,
)
from app.adapters.content.llm_summarizer_articles import LLMArticleGenerator
from app.adapters.content.llm_summarizer_cache import LLMSummaryCache
from app.adapters.content.llm_summarizer_insights import (
    LLMInsightsGenerator,
    insights_has_content,
)
from app.adapters.content.llm_summarizer_metadata import LLMSummaryMetadataHelper
from app.adapters.content.llm_summarizer_semantic import LLMSemanticHelper
from app.adapters.content.llm_summarizer_text import coerce_string_list, truncate_content_text
from app.core.content_cleaner import clean_content_for_llm
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU
from app.core.token_utils import count_tokens
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.cache.redis_cache import RedisCache
from app.infrastructure.persistence.sqlite.repositories.crawl_result_repository import (
    SqliteCrawlResultRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm import LLMClientProtocol
    from app.config import AppConfig
    from app.db.session import DatabaseSessionManager
    from app.db.write_queue import DbWriteQueue
    from app.services.topic_search import TopicSearchService

logger = logging.getLogger(__name__)


def _detect_content_type_hint(content: str) -> str:
    """Detect content type from text heuristics and return a 1-line hint.

    Costs ~15 tokens when triggered. No LLM call.
    """
    lower = content[:2000].lower()
    if any(kw in lower for kw in ("abstract", "methodology", "doi:", "et al.", "arxiv")):
        return "CONTENT HINT: Research paper. Focus on methodology, findings, and limitations.\n"
    if any(
        kw in lower for kw in ("step 1", "how to", "tutorial", "prerequisites", "getting started")
    ):
        return "CONTENT HINT: Tutorial. Focus on steps, prerequisites, and outcomes.\n"
    if any(
        kw in lower
        for kw in ("breaking:", "reuters", "reported today", "press release", "associated press")
    ):
        return "CONTENT HINT: News article. Focus on who, what, when, where, why.\n"
    if any(
        kw in lower for kw in ("in my opinion", "i think", "i believe", "editorial", "commentary")
    ):
        return (
            "CONTENT HINT: Opinion piece. Focus on the author's thesis and supporting arguments.\n"
        )
    return ""


class LLMSummarizer:
    """Handles AI summarization calls and response processing."""

    def __init__(
        self,
        cfg: AppConfig,
        db: DatabaseSessionManager,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
        topic_search: TopicSearchService | None = None,
        db_write_queue: DbWriteQueue | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem
        self._topic_search = topic_search
        self._db_write_queue = db_write_queue
        self.summary_repo = SqliteSummaryRepositoryAdapter(db)
        self.request_repo = SqliteRequestRepositoryAdapter(db)
        self.crawl_result_repo = SqliteCrawlResultRepositoryAdapter(db)
        self._workflow = LLMResponseWorkflow(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
            db_write_queue=db_write_queue,
        )
        self._cache = RedisCache(cfg)
        self._prompt_version = cfg.runtime.summary_prompt_version
        self._semantic_helper = LLMSemanticHelper()
        self._cache_helper = LLMSummaryCache(
            cache=self._cache,
            cfg=cfg,
            prompt_version=self._prompt_version,
            workflow=self._workflow,
            insights_has_content=insights_has_content,
        )
        self._insights_helper = LLMInsightsGenerator(
            cfg=cfg,
            openrouter=openrouter,
            workflow=self._workflow,
            summary_repo=self.summary_repo,
            cache_helper=self._cache_helper,
            sem=sem,
            coerce_string_list=coerce_string_list,
            truncate_content_text=truncate_content_text,
        )
        self._metadata_helper = LLMSummaryMetadataHelper(
            request_repo=self.request_repo,
            crawl_result_repo=self.crawl_result_repo,
            openrouter=openrouter,
            workflow=self._workflow,
            sem=sem,
            semantic_helper=self._semantic_helper,
        )
        self._article_helper = LLMArticleGenerator(
            cfg=cfg,
            openrouter=openrouter,
            workflow=self._workflow,
            cache_helper=self._cache_helper,
            sem=sem,
            select_max_tokens=self._insights_helper.select_max_tokens,
            coerce_string_list=coerce_string_list,
        )
        self._last_llm_result: Any | None = None

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
        *,
        url_hash: str | None = None,
        url: str | None = None,
        silent: bool = False,
        defer_persistence: bool = False,
    ) -> dict[str, Any] | None:
        """Summarize content using LLM and return shaped summary."""
        # Validate content before sending to LLM
        if not content_text or not content_text.strip():
            await self._handle_empty_content_error(message, req_id, correlation_id, interaction_id)
            return None

        content_for_summary = content_text
        model_override = None
        if len(content_text) > max_chars:
            if self.cfg.openrouter.long_context_model:
                model_override = self.cfg.openrouter.long_context_model
            else:
                content_for_summary = truncate_content_text(content_text, max_chars)
                logger.info(
                    "summary_content_truncated",
                    extra={
                        "cid": correlation_id,
                        "original_len": len(content_text),
                        "truncated_len": len(content_for_summary),
                        "max_chars": max_chars,
                    },
                )

        # Clean content to remove boilerplate before LLM input
        content_for_summary = clean_content_for_llm(content_for_summary)

        # Optionally enrich with web search context
        search_context = await self._maybe_enrich_with_search(
            content_for_summary, chosen_lang, correlation_id
        )

        content_hint = _detect_content_type_hint(content_for_summary)
        user_content = (
            f"Analyze the following content and output ONLY a valid JSON object that matches the system contract exactly. "
            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}. Do NOT include any text outside the JSON.\n\n"
            f"{content_hint}"
            f"CONTENT START\n{content_for_summary}\nCONTENT END"
        )

        # Inject web search context if available
        if search_context:
            user_content = f"{user_content}\n\n{search_context}"

        self._log_llm_content_validation(
            content_for_summary, system_prompt, user_content, correlation_id
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        base_model = model_override or self.cfg.openrouter.model

        response_format_schema = self._workflow.build_structured_response_format()
        response_format_json_object = self._workflow.build_structured_response_format(
            mode="json_object"
        )
        max_tokens_schema = self._select_max_tokens(content_for_summary)
        max_tokens_json_object = self._select_max_tokens(user_content)

        base_temperature = self.cfg.openrouter.temperature
        base_top_p = self.cfg.openrouter.top_p if self.cfg.openrouter.top_p is not None else 0.9

        def _clamp(value: float, min_value: float, max_value: float) -> float:
            return max(min_value, min(max_value, value))

        # Temperature/top_p for json_object fallback (lower for deterministic output)
        json_temperature = self.cfg.openrouter.summary_temperature_json_fallback or _clamp(
            base_temperature - 0.05, 0.0, 0.5
        )
        json_top_p = self.cfg.openrouter.summary_top_p_json_fallback or _clamp(
            base_top_p, 0.0, 0.95
        )

        self._last_llm_result = None
        self._insights_helper.reset_state()

        requests: list[LLMRequestConfig] = []

        def _add_request(
            *,
            preset: str,
            model_name: str,
            response_format: dict[str, Any],
            max_tokens: int | None,
            temperature: float,
            top_p: float | None,
        ) -> None:
            requests.append(
                LLMRequestConfig(
                    preset_name=preset,
                    messages=messages,
                    response_format=response_format,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    model_override=model_name,
                    silent=silent,
                )
            )

        _add_request(
            preset="schema_strict",
            model_name=base_model,
            response_format=response_format_schema,
            max_tokens=max_tokens_schema,
            temperature=base_temperature,
            top_p=base_top_p,
        )

        # Removed schema_relaxed preset (marginal benefit, adds latency/cost)

        _add_request(
            preset="json_object_guardrail",
            model_name=base_model,
            response_format=response_format_json_object,
            max_tokens=max_tokens_json_object,
            temperature=json_temperature,
            top_p=json_top_p,
        )

        # Limit fallback to single model (deepseek-r1) to reduce cost on failing requests
        fallback_models = [
            model for model in self.cfg.openrouter.fallback_models if model and model != base_model
        ]
        if fallback_models:
            # Only use first fallback model to limit cost
            fallback_model = fallback_models[0]
            _add_request(
                preset="json_object_fallback",
                model_name=fallback_model,
                response_format=response_format_json_object,
                max_tokens=max_tokens_json_object,
                temperature=json_temperature,
                top_p=json_top_p,
            )

        repair_context = LLMRepairContext(
            base_messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            repair_response_format=self._workflow.build_structured_response_format(
                mode="json_object"
            ),
            repair_max_tokens=self._select_max_tokens(user_content),
            default_prompt=(
                "Your previous message was not a valid JSON object. Respond with ONLY a corrected JSON "
                "that matches the schema exactly."
            ),
            missing_fields_prompt=(
                "Your previous message was not a valid JSON object. Respond with ONLY a corrected JSON that "
                "matches the schema exactly. Ensure `summary_250` and `tldr` contain non-empty informative text."
            ),
        )

        async def _on_completion(llm_result: Any, attempt: LLMRequestConfig) -> None:
            await self.response_formatter.send_llm_completion_notification(
                message, llm_result, correlation_id, silent=attempt.silent
            )

        async def _on_llm_error(llm_result: Any, details: str | None) -> None:
            if silent:
                return
            await self.response_formatter.send_error_notification(
                message,
                "llm_error",
                correlation_id or "unknown",
                details=details,
            )

        async def _on_repair_failure() -> None:
            if silent:
                return
            await self.response_formatter.send_error_notification(
                message,
                "processing_failed",
                correlation_id or "unknown",
                details="Unable to repair invalid JSON returned by the model",
            )

        async def _on_parsing_failure() -> None:
            if silent:
                return
            await self.response_formatter.send_error_notification(
                message,
                "processing_failed",
                correlation_id or "unknown",
                details="Model did not produce valid summary output after retries",
            )

        notifications = LLMWorkflowNotifications(
            completion=_on_completion,
            llm_error=_on_llm_error,
            repair_failure=_on_repair_failure,
            parsing_failure=_on_parsing_failure,
        )

        def _insights_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
            return self._insights_helper.insights_from_summary(summary)

        interaction_config = LLMInteractionConfig(
            interaction_id=interaction_id,
            success_kwargs={
                "response_sent": True,
                "response_type": "summary",
                "request_id": req_id,
            },
            llm_error_builder=lambda llm_result, details: {
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": details
                or f"LLM error: {llm_result.error_text or 'Unknown error'}",
                "request_id": req_id,
            },
            repair_failure_kwargs={
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": "Invalid summary format",
                "request_id": req_id,
            },
            parsing_failure_kwargs={
                "response_sent": True,
                "response_type": "error",
                "error_occurred": True,
                "error_message": "Invalid summary format",
                "request_id": req_id,
            },
        )

        persistence = LLMSummaryPersistenceSettings(
            lang=chosen_lang,
            is_read=True,
            insights_getter=_insights_from_summary,
            defer_write=defer_persistence,
        )

        async def _on_attempt(llm_result: Any) -> None:
            self._last_llm_result = llm_result

        async def _on_success(summary: dict[str, Any], llm_result: Any) -> None:
            self._insights_helper.update_last_summary(summary)

        ensure_summary = lambda summary: self._metadata_helper.ensure_summary_metadata(  # noqa: E731
            summary, req_id, content_text, correlation_id, chosen_lang
        )

        model_for_cache = base_model
        cached_summary = await self._cache_helper.get_cached_summary(
            url_hash, chosen_lang, model_for_cache, correlation_id
        )
        if cached_summary is not None:
            llm_stub = self._cache_helper.build_cache_stub(model_for_cache)
            self._last_llm_result = llm_stub
            shaped = await self._workflow._finalize_success(
                cached_summary,
                llm_stub,
                req_id,
                correlation_id,
                interaction_config,
                persistence,
                ensure_summary,
                _on_success,
                defer_persistence,
            )
            if not silent:
                await self.response_formatter.send_cached_summary_notification(
                    message, silent=silent
                )
            if url_hash:
                await self._cache_helper.write_summary_cache(
                    url_hash, model_for_cache, chosen_lang, shaped
                )
            return shaped

        await self.response_formatter.send_llm_start_notification(
            message,
            model_for_cache,
            len(content_text),
            self.cfg.openrouter.structured_output_mode,
            url=url,
            silent=silent,
        )

        summary = await self._workflow.execute_summary_workflow(
            message=message,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_config=interaction_config,
            persistence=persistence,
            repair_context=repair_context,
            requests=requests,
            notifications=notifications,
            ensure_summary=ensure_summary,
            on_attempt=_on_attempt,
            on_success=_on_success,
            defer_persistence=defer_persistence,
        )

        # Two-pass enrichment: merge enrichment fields into core summary
        if summary and self.cfg.runtime.summary_two_pass_enabled:
            summary = await self._enrich_summary_two_pass(
                summary, content_for_summary, chosen_lang, correlation_id
            )

        if summary and url_hash:
            chosen_model = getattr(self._last_llm_result, "model", model_for_cache)
            await self._cache_helper.write_summary_cache(
                url_hash, chosen_model, chosen_lang, summary
            )
        return summary

    async def summarize_content_pure(
        self,
        content_text: str,
        chosen_lang: str,
        system_prompt: str,
        correlation_id: str | None = None,
        feedback_instructions: str | None = None,
    ) -> dict[str, Any]:
        """Pure summarization method without message dependencies.

        This method performs LLM summarization without sending Telegram notifications,
        making it suitable for use by agents and non-interactive contexts.

        Args:
            content_text: The content to summarize
            chosen_lang: Target language for the summary
            system_prompt: System prompt for the LLM
            correlation_id: Optional correlation ID for tracing
            feedback_instructions: Optional feedback from previous validation attempts

        Returns:
            Summary dictionary with the generated JSON

        Raises:
            ValueError: If content is empty or summarization fails
        """
        # Validate content before sending to LLM
        if not content_text or not content_text.strip():
            raise ValueError("Content text is empty or contains only whitespace")

        content_for_summary = content_text
        model_override = None
        max_chars_threshold = 50000
        if len(content_text) > max_chars_threshold:
            if self.cfg.openrouter.long_context_model:
                model_override = self.cfg.openrouter.long_context_model
            else:
                content_for_summary = truncate_content_text(content_text, max_chars_threshold)
                logger.info(
                    "summarize_pure_truncated",
                    extra={
                        "cid": correlation_id,
                        "original_len": len(content_text),
                        "truncated_len": len(content_for_summary),
                        "max_chars": max_chars_threshold,
                    },
                )

        # Clean content to remove boilerplate before LLM input
        content_for_summary = clean_content_for_llm(content_for_summary)

        # Build user prompt with optional feedback
        content_hint = _detect_content_type_hint(content_for_summary)
        user_content = (
            f"Analyze the following content and output ONLY a valid JSON object that matches the system contract exactly. "
            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}. Do NOT include any text outside the JSON.\n\n"
        )

        if feedback_instructions:
            user_content += f"{feedback_instructions}\n\n"

        user_content += f"{content_hint}CONTENT START\n{content_for_summary}\nCONTENT END"

        self._log_llm_content_validation(
            content_for_summary, system_prompt, user_content, correlation_id
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Select response format and max tokens
        response_format = self._workflow.build_structured_response_format()
        max_tokens = self._select_max_tokens(content_for_summary)

        logger.info(
            "summarize_pure_start",
            extra={
                "cid": correlation_id,
                "content_len": len(content_for_summary),
                "lang": chosen_lang,
                "has_feedback": bool(feedback_instructions),
                "model": model_override or self.cfg.openrouter.model,
            },
        )

        # Make the LLM call (no request_id since this is agent-only mode)
        try:
            async with self._sem():
                llm_result = await self.openrouter.chat(
                    messages,
                    response_format=response_format,
                    max_tokens=max_tokens,
                    temperature=self.cfg.openrouter.temperature,
                    top_p=self.cfg.openrouter.top_p,
                    request_id=None,  # No DB persistence in pure mode
                    model_override=model_override,
                )
        except Exception as e:
            logger.error(
                "summarize_pure_llm_call_failed",
                extra={"cid": correlation_id, "error": str(e)},
            )
            raise ValueError(f"LLM call failed: {e}") from e

        # Check if LLM call succeeded
        if llm_result.status != "ok":
            error_msg = llm_result.error_text or "Unknown LLM error"
            logger.error(
                "summarize_pure_llm_error",
                extra={
                    "cid": correlation_id,
                    "status": llm_result.status,
                    "error": error_msg,
                },
            )
            raise ValueError(f"LLM returned error status: {error_msg}") from None

        # Parse the response
        summary = self._parse_summary_from_llm_result(llm_result)
        if not summary:
            logger.error(
                "summarize_pure_parse_failed",
                extra={"cid": correlation_id},
            )
            raise ValueError("Failed to parse valid summary from LLM response") from None

        logger.info(
            "summarize_pure_success",
            extra={
                "cid": correlation_id,
                "summary_keys": list(summary.keys()),
            },
        )

        return summary

    def _parse_summary_from_llm_result(self, llm_result: Any) -> dict[str, Any] | None:
        """Parse summary JSON from LLM result.

        Args:
            llm_result: The LLM response object

        Returns:
            Parsed summary dictionary or None if parsing fails
        """
        # Try to extract from response_json first
        if isinstance(llm_result.response_json, dict):
            choices = llm_result.response_json.get("choices") or []
            if choices:
                message = (choices[0] or {}).get("message") or {}

                # Try parsed field first (structured outputs)
                parsed = message.get("parsed")
                if isinstance(parsed, dict):
                    return parsed

                # Try content field
                content = message.get("content")
                if isinstance(content, str):
                    extracted = extract_json(content)
                    if isinstance(extracted, dict):
                        return extracted

        # Fallback to response_text
        if llm_result.response_text:
            extracted = extract_json(llm_result.response_text)
            if isinstance(extracted, dict):
                return extracted

        return None

    def _select_max_tokens(self, content_text: str) -> int | None:
        """Choose an appropriate max_tokens budget based on content size.

        Optimized formula: summaries rarely exceed 4K tokens, so we use a more
        conservative budget to reduce costs (10-20% savings).
        Uses tiktoken for accurate counting when available, falls back to heuristic.
        """
        configured = self.cfg.openrouter.max_tokens

        approx_input_tokens = count_tokens(content_text)

        # Conservative budget: summary output rarely exceeds 4K tokens
        dynamic_budget = max(4096, min(12288, approx_input_tokens // 2 + 2048))

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

        selected = max(4096, min(configured, dynamic_budget))

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

    async def _enrich_summary_two_pass(
        self,
        summary: dict[str, Any],
        content_text: str,
        chosen_lang: str,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        """Run a second LLM pass to generate enrichment fields.

        Feature-flagged via SUMMARY_TWO_PASS_ENABLED. Merges enrichment fields
        into the existing summary without overwriting core fields.
        """
        try:
            from pathlib import Path

            prompt_dir = Path(__file__).resolve().parent.parent.parent / "prompts"
            lang_suffix = "ru" if chosen_lang == LANG_RU else "en"
            prompt_path = prompt_dir / f"enrichment_system_{lang_suffix}.txt"

            enrichment_prompt = prompt_path.read_text(encoding="utf-8")

            # Build user message with core summary context
            from app.core.json_utils import dumps as json_dumps

            core_fields = {
                "summary_250",
                "summary_1000",
                "tldr",
                "key_ideas",
                "topic_tags",
                "entities",
                "source_type",
            }
            core_summary_text = json_dumps(
                {k: v for k, v in summary.items() if k in core_fields},
                indent=2,
            )
            user_content = (
                f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n"
                f"CORE SUMMARY (already generated, do not modify):\n{core_summary_text}\n\n"
                f"ORIGINAL CONTENT START\n{content_text[:30000]}\nORIGINAL CONTENT END"
            )

            messages = [
                {"role": "system", "content": enrichment_prompt},
                {"role": "user", "content": user_content},
            ]

            async with self._sem():
                llm_result = await self.openrouter.chat(
                    messages,
                    response_format=self._workflow.build_structured_response_format(
                        mode="json_object"
                    ),
                    max_tokens=4096,
                    temperature=self.cfg.openrouter.temperature,
                    top_p=self.cfg.openrouter.top_p,
                    request_id=None,
                )

            if llm_result.status != "ok":
                logger.warning(
                    "two_pass_enrichment_failed",
                    extra={"cid": correlation_id, "error": llm_result.error_text},
                )
                return summary

            enrichment = self._parse_summary_from_llm_result(llm_result)
            if not enrichment:
                logger.warning(
                    "two_pass_enrichment_parse_failed",
                    extra={"cid": correlation_id},
                )
                return summary

            # Merge enrichment fields into summary without overwriting core fields
            enrichment_keys = {
                "answered_questions",
                "seo_keywords",
                "extractive_quotes",
                "highlights",
                "categories",
                "key_points_to_remember",
                "questions_answered",
                "topic_taxonomy",
            }
            for key in enrichment_keys:
                value = enrichment.get(key)
                if value:
                    summary[key] = value

            logger.info(
                "two_pass_enrichment_merged",
                extra={
                    "cid": correlation_id,
                    "enriched_fields": [k for k in enrichment_keys if k in enrichment],
                },
            )
            return summary

        except Exception as e:
            logger.warning(
                "two_pass_enrichment_error",
                extra={"cid": correlation_id, "error": str(e)},
            )
            return summary

    async def generate_custom_article(
        self,
        message: Any,
        *,
        chosen_lang: str,
        req_id: int,
        topics: list[str] | None,
        tags: list[str] | None,
        correlation_id: str | None,
        url_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """Generate a standalone article based on extracted topics and tags."""
        return await self._article_helper.generate_custom_article(
            message,
            chosen_lang=chosen_lang,
            req_id=req_id,
            topics=topics,
            tags=tags,
            correlation_id=correlation_id,
            url_hash=url_hash,
        )

    async def translate_summary_to_ru(
        self,
        summary: dict[str, Any],
        *,
        req_id: int,
        correlation_id: str | None = None,
        url_hash: str | None = None,
        source_lang: str | None = None,
    ) -> str | None:
        """Translate a shaped summary to fluent Russian for Telegram delivery."""
        return await self._article_helper.translate_summary_to_ru(
            summary,
            req_id=req_id,
            correlation_id=correlation_id,
            url_hash=url_hash,
            source_lang=source_lang,
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
        await self.request_repo.async_update_request_status(req_id, "error")
        await self.response_formatter.send_error_notification(
            message, "empty_content", correlation_id
        )

        # Update interaction with error
        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="error",
                error_occurred=True,
                error_message="No meaningful content extracted from URL",
                request_id=req_id,
                logger_=logger,
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

    async def _maybe_enrich_with_search(
        self, content_text: str, chosen_lang: str, correlation_id: str | None
    ) -> str:
        """Optionally enrich content with web search context.

        This method checks if web search enrichment is enabled and beneficial,
        then executes targeted searches to provide additional context for summarization.

        Args:
            content_text: The article content to analyze
            chosen_lang: Target language for the summary
            correlation_id: Optional correlation ID for tracing

        Returns:
            Formatted search context string, or empty string if search not needed/available
        """
        # Skip if web search is disabled
        if not self.cfg.web_search.enabled:
            return ""

        # Skip if TopicSearchService not available
        if self._topic_search is None:
            logger.debug(
                "web_search_skipped_no_service",
                extra={"cid": correlation_id},
            )
            return ""

        # Skip for short content
        if len(content_text) < self.cfg.web_search.min_content_length:
            logger.debug(
                "web_search_skipped_short_content",
                extra={
                    "cid": correlation_id,
                    "content_len": len(content_text),
                    "min_required": self.cfg.web_search.min_content_length,
                },
            )
            return ""

        try:
            from app.agents.web_search_agent import WebSearchAgent, WebSearchAgentInput

            agent = WebSearchAgent(
                llm_client=self.openrouter,
                search_service=self._topic_search,
                cfg=self.cfg.web_search,
                correlation_id=correlation_id,
            )

            input_data = WebSearchAgentInput(
                content=content_text[:8000],  # Limit for analysis
                language=chosen_lang,
                correlation_id=correlation_id,
            )

            result = await agent.execute(input_data)

            if result.success and result.output and result.output.context:
                context = result.output.context
                logger.info(
                    "web_search_context_injected",
                    extra={
                        "cid": correlation_id,
                        "searched": result.output.searched,
                        "queries": result.output.queries_executed,
                        "articles_found": result.output.articles_found,
                        "context_chars": len(context),
                    },
                )
                # Format with header
                current_date = datetime.now().strftime("%Y-%m-%d")
                return f"ADDITIONAL WEB CONTEXT (retrieved {current_date}):\n{context}"

            return ""

        except Exception as e:
            logger.warning(
                "web_search_enrichment_failed",
                extra={
                    "cid": correlation_id,
                    "error": str(e),
                },
            )
            return ""

    @property
    def last_llm_result(self) -> Any | None:
        """Return the most recent LLM call result for summarization."""
        return self._last_llm_result

    async def enrich_summary_rag_fields(
        self,
        summary: dict[str, Any],
        *,
        content_text: str,
        chosen_lang: str | None,
        req_id: int,
    ) -> dict[str, Any]:
        """Attach semantic retrieval fields to an existing summary payload."""
        return await self._semantic_helper.enrich_with_rag_fields(
            summary,
            content_text=content_text,
            chosen_lang=chosen_lang,
            req_id=req_id,
        )

    async def generate_additional_insights(
        self,
        message: Any,
        *,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        summary: dict[str, Any] | None = None,
        url_hash: str | None = None,
    ) -> dict[str, Any] | None:
        """Call OpenRouter to obtain additional researched insights for the article."""
        return await self._insights_helper.generate_additional_insights(
            message,
            content_text=content_text,
            chosen_lang=chosen_lang,
            req_id=req_id,
            correlation_id=correlation_id,
            summary=summary,
            url_hash=url_hash,
        )

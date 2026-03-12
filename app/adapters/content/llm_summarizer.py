"""LLM summarization and response processing."""

from __future__ import annotations

import logging
import time
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
from app.adapters.external.formatting.single_url_progress_formatter import (
    SingleURLProgressFormatter,
)
from app.adapters.repository_ports import (
    CrawlResultRepositoryPort,
    RequestRepositoryPort,
    SummaryRepositoryPort,
    create_crawl_result_repository,
    create_request_repository,
    create_summary_repository,
)
from app.core.content_cleaner import clean_content_for_llm
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU
from app.core.summary_contract import validate_and_shape_summary
from app.core.token_utils import count_tokens
from app.db.user_interactions import async_safe_update_user_interaction
from app.infrastructure.cache.redis_cache import RedisCache
from app.utils.progress_message_updater import ProgressMessageUpdater
from app.utils.typing_indicator import typing_indicator

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm import LLMClientProtocol
    from app.config import AppConfig
    from app.core.progress_tracker import ProgressTracker
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


def _clamp_float(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _build_summary_requests_for(
    summarizer: LLMSummarizer,
    *,
    messages: list[dict[str, Any]],
    base_model: str,
    content_for_summary: str,
    user_content: str,
    silent: bool,
) -> list[LLMRequestConfig]:
    """Construct ordered LLM request attempts for summary generation."""
    response_format_schema = summarizer._workflow.build_structured_response_format()
    response_format_json_object = summarizer._workflow.build_structured_response_format(
        mode="json_object"
    )
    max_tokens_schema = summarizer._select_max_tokens(content_for_summary)
    max_tokens_json_object = summarizer._select_max_tokens(user_content)
    base_temperature = summarizer.cfg.openrouter.temperature
    base_top_p = (
        summarizer.cfg.openrouter.top_p if summarizer.cfg.openrouter.top_p is not None else 0.9
    )

    json_temperature = summarizer.cfg.openrouter.summary_temperature_json_fallback or _clamp_float(
        base_temperature - 0.05, 0.0, 0.5
    )
    json_top_p = summarizer.cfg.openrouter.summary_top_p_json_fallback or _clamp_float(
        base_top_p, 0.0, 0.95
    )

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
    _add_request(
        preset="json_object_guardrail",
        model_name=base_model,
        response_format=response_format_json_object,
        max_tokens=max_tokens_json_object,
        temperature=json_temperature,
        top_p=json_top_p,
    )

    fallback_models = [
        model
        for model in summarizer.cfg.openrouter.fallback_models
        if model and model != base_model
    ]
    flash_models: list[str] = []
    flash_model = getattr(summarizer.cfg.openrouter, "flash_model", None)
    if flash_model:
        flash_models.append(flash_model)
    flash_fallback_models = getattr(summarizer.cfg.openrouter, "flash_fallback_models", [])
    if flash_fallback_models:
        flash_models.extend(flash_fallback_models)

    added_flash_models: set[str] = set()
    for model_name in flash_models:
        if model_name and model_name != base_model and model_name not in added_flash_models:
            _add_request(
                preset="json_object_flash",
                model_name=model_name,
                response_format=response_format_json_object,
                max_tokens=max_tokens_json_object,
                temperature=json_temperature,
                top_p=json_top_p,
            )
            added_flash_models.add(model_name)

    if fallback_models:
        fallback_model = fallback_models[0]
        if fallback_model not in added_flash_models:
            _add_request(
                preset="json_object_fallback",
                model_name=fallback_model,
                response_format=response_format_json_object,
                max_tokens=max_tokens_json_object,
                temperature=json_temperature,
                top_p=json_top_p,
            )
    return requests


async def _execute_summary_with_progress_for(
    summarizer: LLMSummarizer,
    *,
    message: Any,
    req_id: int,
    correlation_id: str | None,
    interaction_config: LLMInteractionConfig,
    persistence: LLMSummaryPersistenceSettings,
    repair_context: LLMRepairContext,
    requests: list[LLMRequestConfig],
    notifications: LLMWorkflowNotifications,
    ensure_summary: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
    on_attempt: Callable[[Any], Awaitable[None]],
    on_success: Callable[[dict[str, Any], Any], Awaitable[None]],
    defer_persistence: bool,
    progress_tracker: ProgressTracker | None,
    content_for_summary: str,
    model_for_cache: str,
    chosen_lang: str,
) -> dict[str, Any] | None:
    """Run workflow with reader progress updates or debug typing indicator."""
    use_progress = progress_tracker is not None
    updater: ProgressMessageUpdater | None = None
    typing_ctx: Any = None
    start_time = time.time()

    try:
        if use_progress and progress_tracker is not None:
            updater = ProgressMessageUpdater(progress_tracker, message)

            def analyzing_formatter(elapsed: float) -> str:
                return SingleURLProgressFormatter.format_llm_progress(
                    content_length=len(content_for_summary),
                    model=model_for_cache,
                    elapsed_sec=elapsed,
                    phase="analyzing",
                )

            await updater.start(analyzing_formatter)
        else:
            typing_ctx = typing_indicator(summarizer.response_formatter, message, action="typing")
            await typing_ctx.__aenter__()

        summary = await summarizer._workflow.execute_summary_workflow(
            message=message,
            req_id=req_id,
            correlation_id=correlation_id,
            interaction_config=interaction_config,
            persistence=persistence,
            repair_context=repair_context,
            requests=requests,
            notifications=notifications,
            ensure_summary=ensure_summary,
            on_attempt=on_attempt,
            on_success=on_success,
            defer_persistence=defer_persistence,
        )

        if summary and summarizer.cfg.runtime.summary_two_pass_enabled:
            if use_progress and updater is not None:

                def enriching_formatter(elapsed: float) -> str:
                    return SingleURLProgressFormatter.format_llm_progress(
                        content_length=len(content_for_summary),
                        model=model_for_cache,
                        elapsed_sec=elapsed,
                        phase="enriching",
                    )

                await updater.update_formatter(enriching_formatter)
            summary = await summarizer._enrich_summary_two_pass(
                summary, content_for_summary, chosen_lang, correlation_id
            )

        elapsed_total = time.time() - start_time
        if use_progress and updater is not None:
            success_msg = SingleURLProgressFormatter.format_llm_complete(
                model=model_for_cache,
                elapsed_sec=elapsed_total,
                success=summary is not None,
                correlation_id=correlation_id if summary is None else None,
            )
            await updater.finalize(success_msg)
        elif typing_ctx:
            await typing_ctx.__aexit__(None, None, None)
        return summary
    except Exception:
        if use_progress and updater is not None:
            error_msg = SingleURLProgressFormatter.format_llm_complete(
                model=model_for_cache,
                elapsed_sec=time.time() - start_time,
                success=False,
                error_msg="Processing failed",
                correlation_id=correlation_id,
            )
            await updater.finalize(error_msg)
        elif typing_ctx:
            await typing_ctx.__aexit__(None, None, None)
        raise


def _summary_streaming_enabled_for(summarizer: Any, *, silent: bool) -> bool:
    if silent:
        return False
    if not getattr(summarizer.cfg.runtime, "summary_streaming_enabled", True):
        return False
    if getattr(summarizer.cfg.runtime, "summary_streaming_mode", "section") != "section":
        return False
    telegram_cfg = getattr(summarizer.cfg, "telegram", None)
    if telegram_cfg is None:
        return False
    if not getattr(telegram_cfg, "draft_streaming_enabled", True):
        return False

    scope = getattr(summarizer.cfg.runtime, "summary_streaming_provider_scope", "openrouter")
    scope = str(scope).strip().lower()
    if scope == "disabled":
        return False
    if scope == "all":
        return True
    provider_name = str(getattr(summarizer.openrouter, "provider_name", "openrouter")).lower()
    return provider_name == scope


def _configure_summary_streaming_for(
    summarizer: Any,
    *,
    requests: list[LLMRequestConfig],
    message: Any,
    correlation_id: str | None,
    silent: bool,
) -> Any | None:
    if not _summary_streaming_enabled_for(summarizer, silent=silent):
        return None
    from app.adapters.telegram.summary_draft_streaming import SummaryDraftStreamCoordinator

    stream_coordinator = SummaryDraftStreamCoordinator(
        response_formatter=summarizer.response_formatter,
        message=message,
        correlation_id=correlation_id,
    )
    for request in requests:
        request.stream = True
        request.on_stream_delta = stream_coordinator.on_delta
    return stream_coordinator


async def _prepare_summary_content_for(
    summarizer: LLMSummarizer,
    *,
    content_text: str,
    max_chars: int,
    correlation_id: str | None,
    images: list[str] | None,
) -> tuple[str, str | None]:
    """Choose model override/truncation strategy and return cleaned content."""
    content_for_summary = content_text
    model_override = summarizer.cfg.attachment.vision_model if images else None

    if len(content_text) > max_chars:
        if summarizer.cfg.openrouter.long_context_model:
            model_override = summarizer.cfg.openrouter.long_context_model
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

    content_for_summary = clean_content_for_llm(content_for_summary)

    return content_for_summary, model_override


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
        summary_repo: SummaryRepositoryPort | None = None,
        request_repo: RequestRepositoryPort | None = None,
        crawl_result_repo: CrawlResultRepositoryPort | None = None,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem
        self._topic_search = topic_search
        self._db_write_queue = db_write_queue
        self.summary_repo = summary_repo or create_summary_repository(db)
        self.request_repo = request_repo or create_request_repository(db)
        self.crawl_result_repo = crawl_result_repo or create_crawl_result_repository(db)
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

    @property
    def workflow(self) -> LLMResponseWorkflow:
        """Access the internal LLM interaction workflow."""
        return self._workflow

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
        on_phase_change: Callable[[str, str | None, int | None, str | None], Awaitable[None]]
        | None = None,
        images: list[str] | None = None,
        progress_tracker: ProgressTracker | None = None,
    ) -> dict[str, Any] | None:
        """Summarize content using LLM and return shaped summary."""
        # Validate content before sending to LLM
        if not content_text or not content_text.strip():
            await self._handle_empty_content_error(message, req_id, correlation_id, interaction_id)
            return None

        content_for_summary, model_override = await _prepare_summary_content_for(
            self,
            content_text=content_text,
            max_chars=max_chars,
            correlation_id=correlation_id,
            images=images,
        )
        search_context = await self._maybe_enrich_with_search(
            content_for_summary, chosen_lang, correlation_id
        )
        user_content = self._build_summary_user_content(
            content_for_summary=content_for_summary,
            chosen_lang=chosen_lang,
            search_context=search_context,
        )
        self._log_llm_content_validation(
            content_for_summary, system_prompt, user_content, correlation_id
        )
        messages = self._build_summary_messages(system_prompt, user_content, images=images)

        base_model = model_override or self.cfg.openrouter.model
        self._last_llm_result = None
        self._insights_helper.reset_state()

        requests = _build_summary_requests_for(
            self,
            messages=messages,
            base_model=base_model,
            content_for_summary=content_for_summary,
            user_content=user_content,
            silent=silent,
        )
        stream_coordinator = _configure_summary_streaming_for(
            self,
            requests=requests,
            message=message,
            correlation_id=correlation_id,
            silent=silent,
        )

        repair_context = self._build_summary_repair_context(system_prompt, user_content)
        notifications = self._build_summary_notifications(
            message=message,
            correlation_id=correlation_id,
            silent=silent,
            on_phase_change=on_phase_change,
        )
        interaction_config = self._build_summary_interaction_config(
            interaction_id=interaction_id,
            req_id=req_id,
        )
        persistence = self._build_summary_persistence_settings(
            chosen_lang=chosen_lang,
            defer_persistence=defer_persistence,
        )

        return await self._run_summary_pipeline(
            message=message,
            content_text=content_text,
            chosen_lang=chosen_lang,
            req_id=req_id,
            correlation_id=correlation_id,
            url_hash=url_hash,
            url=url,
            silent=silent,
            defer_persistence=defer_persistence,
            interaction_config=interaction_config,
            persistence=persistence,
            repair_context=repair_context,
            notifications=notifications,
            requests=requests,
            progress_tracker=progress_tracker,
            content_for_summary=content_for_summary,
            base_model=base_model,
            stream_coordinator=stream_coordinator,
        )

    async def _run_summary_pipeline(
        self,
        *,
        message: Any,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        url_hash: str | None,
        url: str | None,
        silent: bool,
        defer_persistence: bool,
        interaction_config: LLMInteractionConfig,
        persistence: LLMSummaryPersistenceSettings,
        repair_context: LLMRepairContext,
        notifications: LLMWorkflowNotifications,
        requests: list[LLMRequestConfig],
        progress_tracker: ProgressTracker | None,
        content_for_summary: str,
        base_model: str,
        stream_coordinator: Any | None,
    ) -> dict[str, Any] | None:
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
            return await self._finalize_cached_summary(
                message=message,
                cached_summary=cached_summary,
                model_for_cache=model_for_cache,
                req_id=req_id,
                correlation_id=correlation_id,
                interaction_config=interaction_config,
                persistence=persistence,
                ensure_summary=ensure_summary,
                on_success=_on_success,
                defer_persistence=defer_persistence,
                chosen_lang=chosen_lang,
                url_hash=url_hash,
                silent=silent,
            )

        await self.response_formatter.send_llm_start_notification(
            message,
            model_for_cache,
            len(content_text),
            self.cfg.openrouter.structured_output_mode,
            url=url,
            silent=silent,
        )
        try:
            summary = await _execute_summary_with_progress_for(
                self,
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
                progress_tracker=progress_tracker,
                content_for_summary=content_for_summary,
                model_for_cache=model_for_cache,
                chosen_lang=chosen_lang,
            )
        finally:
            if stream_coordinator is not None:
                await stream_coordinator.finalize()

        if summary and url_hash:
            chosen_model = getattr(self._last_llm_result, "model", model_for_cache)
            await self._cache_helper.write_summary_cache(
                url_hash, chosen_model, chosen_lang, summary
            )
        return summary

    def _build_summary_user_content(
        self,
        *,
        content_for_summary: str,
        chosen_lang: str,
        search_context: str,
    ) -> str:
        """Build user payload used for summary generation requests."""
        content_hint = _detect_content_type_hint(content_for_summary)
        user_content = (
            "Analyze the following content and output ONLY a valid JSON object that matches "
            "the system contract exactly. "
            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}. "
            "Do NOT include any text outside the JSON.\n\n"
            f"{content_hint}"
            f"CONTENT START\n{content_for_summary}\nCONTENT END"
        )
        if search_context:
            return f"{user_content}\n\n{search_context}"
        return user_content

    def _build_summary_messages(
        self,
        system_prompt: str,
        user_content: str,
        *,
        images: list[str] | None,
    ) -> list[dict[str, Any]]:
        """Build chat messages, with optional multimodal input parts."""
        if not images:
            return [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

        content_parts: list[dict[str, Any]] = [{"type": "text", "text": user_content}]
        for uri in images:
            content_parts.append({"type": "image_url", "image_url": {"url": uri}})

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content_parts},
        ]

    def _build_summary_repair_context(
        self, system_prompt: str, user_content: str
    ) -> LLMRepairContext:
        """Create fallback/repair settings for invalid JSON model replies."""
        return LLMRepairContext(
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

    def _build_summary_notifications(
        self,
        *,
        message: Any,
        correlation_id: str | None,
        silent: bool,
        on_phase_change: Callable[[str, str | None, int | None, str | None], Awaitable[None]]
        | None,
    ) -> LLMWorkflowNotifications:
        """Build workflow callbacks for completion/retry/error notifications."""

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

        async def _on_retry() -> None:
            if on_phase_change:
                await on_phase_change("retrying", None, None, None)

        return LLMWorkflowNotifications(
            completion=_on_completion,
            llm_error=_on_llm_error,
            repair_failure=_on_repair_failure,
            parsing_failure=_on_parsing_failure,
            retry=_on_retry,
        )

    def _build_summary_interaction_config(
        self, *, interaction_id: int | None, req_id: int
    ) -> LLMInteractionConfig:
        """Build interaction update payloads for workflow outcomes."""
        return LLMInteractionConfig(
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

    def _build_summary_persistence_settings(
        self, *, chosen_lang: str, defer_persistence: bool
    ) -> LLMSummaryPersistenceSettings:
        """Build persistence settings for summary storage."""

        def _insights_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
            return self._insights_helper.insights_from_summary(summary)

        return LLMSummaryPersistenceSettings(
            lang=chosen_lang,
            is_read=True,
            insights_getter=_insights_from_summary,
            defer_write=defer_persistence,
        )

    async def _finalize_cached_summary(
        self,
        *,
        message: Any,
        cached_summary: dict[str, Any],
        model_for_cache: str,
        req_id: int,
        correlation_id: str | None,
        interaction_config: LLMInteractionConfig,
        persistence: LLMSummaryPersistenceSettings,
        ensure_summary: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        on_success: Callable[[dict[str, Any], Any], Awaitable[None]],
        defer_persistence: bool,
        chosen_lang: str,
        url_hash: str | None,
        silent: bool,
    ) -> dict[str, Any]:
        """Finalize summary flow when cached payload is available."""
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
            on_success,
            defer_persistence,
        )
        if not silent:
            await self.response_formatter.send_cached_summary_notification(message, silent=silent)
        if url_hash:
            await self._cache_helper.write_summary_cache(
                url_hash, model_for_cache, chosen_lang, shaped
            )
        return shaped

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

    async def ensure_summary_payload(
        self,
        summary: dict[str, Any],
        *,
        req_id: int,
        content_text: str,
        chosen_lang: str,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Normalize and enrich a parsed summary payload for persistence."""
        if not isinstance(summary, dict):
            raise ValueError("Summary payload must be a dictionary")

        shaped = validate_and_shape_summary(summary)
        shaped = await self._metadata_helper.ensure_summary_metadata(
            shaped, req_id, content_text, correlation_id, chosen_lang
        )
        self._insights_helper.update_last_summary(shaped)
        return shaped

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
        """Enrich content with web search context if enabled and beneficial."""
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

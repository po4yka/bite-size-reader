"""LLM summarization and response processing."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

try:
    from unittest.mock import AsyncMock
except ImportError:  # pragma: no cover - AsyncMock introduced in stdlib py3.8+
    AsyncMock = None  # type: ignore[misc]

from app.adapters.content.llm_response_workflow import (
    LLMInteractionConfig,
    LLMRepairContext,
    LLMRequestConfig,
    LLMResponseWorkflow,
    LLMSummaryPersistenceSettings,
    LLMWorkflowNotifications,
)
from app.config import AppConfig
from app.core.async_utils import raise_if_cancelled
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.openrouter.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)


_STRING_LIST_SPLITTER_RE = re.compile(r"[\n\r•;]+")


class LLMSummarizer:
    """Handles AI summarization calls and response processing."""

    _METADATA_FIELDS: tuple[str, ...] = (
        "title",
        "canonical_url",
        "domain",
        "author",
        "published_at",
        "last_updated",
    )
    _LLM_METADATA_FIELDS: tuple[str, ...] = ("title", "author", "published_at", "last_updated")
    _FIRECRAWL_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
        "title": (
            "title",
            "og:title",
            "og_title",
            "meta_title",
            "twitter:title",
            "headline",
            "dc.title",
            "article:title",
        ),
        "canonical_url": (
            "canonical",
            "canonical_url",
            "og:url",
            "og_url",
            "url",
        ),
        "author": (
            "author",
            "article:author",
            "byline",
            "twitter:creator",
            "dc.creator",
            "creator",
        ),
        "published_at": (
            "article:published_time",
            "article:published",
            "article:publish_time",
            "article:publish_date",
            "datepublished",
            "date_published",
            "publish_date",
            "published",
            "pubdate",
        ),
        "last_updated": (
            "article:modified_time",
            "article:updated_time",
            "date_modified",
            "datemodified",
            "updated",
            "lastmod",
            "last_modified",
        ),
    }

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
        self._workflow = LLMResponseWorkflow(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )
        self._last_llm_result: Any | None = None
        self._last_summary_shaped: dict[str, Any] | None = None
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
        *,
        silent: bool = False,
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

        # Notify: Starting LLM call
        await self.response_formatter.send_llm_start_notification(
            message,
            self.cfg.openrouter.model,
            len(content_text),
            self.cfg.openrouter.structured_output_mode,
            silent=silent,
        )

        # If we have a long-context model configured and content exceeds threshold,
        # prefer a single-pass summary using that model (avoids chunking multi-calls).
        model_override = None
        if len(content_text) > max_chars and (self.cfg.openrouter.long_context_model or ""):
            model_override = self.cfg.openrouter.long_context_model

        response_format = self._workflow.build_structured_response_format()
        max_tokens = self._select_max_tokens(content_text)

        self._last_llm_result = None
        self._last_summary_shaped = None
        self._last_insights = None

        requests: list[LLMRequestConfig] = [
            LLMRequestConfig(
                messages=messages,
                response_format=response_format,
                max_tokens=max_tokens,
                temperature=self.cfg.openrouter.temperature,
                top_p=self.cfg.openrouter.top_p,
                model_override=model_override,
                silent=silent,
            )
        ]

        fallback_models = [
            model
            for model in self.cfg.openrouter.fallback_models
            if model and model != (model_override or self.cfg.openrouter.model)
        ]
        if fallback_models:
            fallback_format = self._workflow.build_structured_response_format(mode="json_object")
            fallback_tokens = self._select_max_tokens(user_content)
            for model_name in fallback_models:
                requests.append(
                    LLMRequestConfig(
                        messages=messages,
                        response_format=fallback_format,
                        max_tokens=fallback_tokens,
                        temperature=self.cfg.openrouter.temperature,
                        top_p=self.cfg.openrouter.top_p,
                        model_override=model_name,
                        silent=silent,
                    )
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
            await self.response_formatter.send_error_notification(
                message,
                "llm_error",
                correlation_id or "unknown",
                details=details,
            )

        async def _on_repair_failure() -> None:
            await self.response_formatter.send_error_notification(
                message,
                "processing_failed",
                correlation_id or "unknown",
                details="Unable to repair invalid JSON returned by the model",
            )

        async def _on_parsing_failure() -> None:
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
            insights_payload = summary.get("insights")
            if isinstance(insights_payload, dict) and self._insights_has_content(insights_payload):
                return insights_payload
            return None

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
        )

        async def _on_attempt(llm_result: Any) -> None:
            self._last_llm_result = llm_result

        async def _on_success(summary: dict[str, Any], llm_result: Any) -> None:
            self._last_summary_shaped = summary
            self._last_insights = _insights_from_summary(summary)

        ensure_summary = lambda summary: self._ensure_summary_metadata(  # noqa: E731
            summary, req_id, content_text, correlation_id
        )

        return await self._workflow.execute_summary_workflow(
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
        )

    def _select_max_tokens(self, content_text: str) -> int | None:
        """Choose an appropriate max_tokens budget based on content size."""
        configured = self.cfg.openrouter.max_tokens

        approx_input_tokens = max(1, len(content_text) // 3)

        model_name = self.cfg.openrouter.model.lower()
        if "gpt-5" in model_name:
            dynamic_budget = max(12288, min(32768, approx_input_tokens + 8192))
            if configured is not None and configured < 20000:
                logger.info(
                    "gpt5_max_tokens_override",
                    extra={
                        "model": self.cfg.openrouter.model,
                        "original_configured": configured,
                        "new_budget": dynamic_budget,
                    },
                )
                configured = None
        else:
            dynamic_budget = max(8192, min(24576, approx_input_tokens + 4096))

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

                    await self._workflow.persist_llm_call(llm, req_id, correlation_id)

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
            raise_if_cancelled(exc)
            logger.exception(
                "custom_article_generation_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            return None

    def _build_article_system_prompt(self, lang: str) -> str:
        if lang == LANG_RU:
            return (
                "Ты ведущий редактор-аналитик. На основе тем и тэгов подготовь"
                " обстоятельную самостоятельную статью, объясняя контекст,"
                " ключевые события, последствия и перспективы. Поддерживай"
                " связное повествование, используй подзаголовок, H2/H3-разделы,"
                " фактические детали и списки, когда уместно. Верни строго JSON"
                " по заданной схеме."
            )
        return (
            "You are a senior long-form editor and analyst. Using the provided topics"
            " and tags, craft a comprehensive standalone article that explains"
            " context, key developments, implications, and outlook. Maintain a clear"
            " narrative, include a short subtitle, structured H2/H3 sections,"
            " concrete details, and bullet lists when helpful. Return strictly as"
            " JSON per the schema."
        )

    def _build_article_user_prompt(self, topics: list[str], tags: list[str], lang: str) -> str:
        lang_label = "Russian" if lang == LANG_RU else "English"
        topics_text = "\n".join(f"- {t}" for t in topics[:12]) or "- (none)"
        tags_text = "\n".join(f"- {t}" for t in tags[:12]) or "- (none)"
        return (
            f"Respond in {lang_label}."
            "\nReturn JSON only with exactly these keys (no extras):"
            '\n{\n  "title": string,\n  "subtitle": string | null,\n  "article_markdown": string,\n  "highlights": [string],\n'
            '"suggested_sources": [string]\n}'
            "\nGuidelines:"
            "\n- `article_markdown` must be a detailed 600-900 word Markdown article with"
            " an engaging introduction, at least four `##` sections, optional `###`"
            " subsections, and short paragraphs (2-3 sentences)."
            "\n- Cover background/context, the current landscape, key drivers or"
            " challenges, stakeholder perspectives, quantitative examples or"
            " milestones, and forward-looking implications or recommendations."
            "\n- Weave provided topics and tags naturally as keywords and explain the"
            " relationships between them."
            "\n- Close with a concise conclusion summarizing takeaways."
            "\n- Provide 5-7 highlight bullet points, each under 160 characters and"
            " capturing distinct insights."
            "\n- Provide 4-6 reputable suggested sources (URLs or publication names);"
            " avoid duplicates and low-quality outlets."
            "\n- Strings may exceed 400 characters when necessary, but keep highlight"
            " and source entries succinct. Use empty arrays when you truly lack"
            " items, but never omit required keys."
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

            # Normalise common body field variants before attempting to coerce sections
            body_keys_precedence: tuple[str, ...] = (
                "article_markdown",
                "articleBody",
                "articleBodyMarkdown",
                "articleMarkdown",
                "body_markdown",
                "bodyMarkdown",
                "body",
                "markdown",
                "content_markdown",
            )
            if "article_markdown" not in candidate:
                for key in body_keys_precedence:
                    if key in candidate and candidate.get(key):
                        candidate["article_markdown"] = candidate.get(key)
                        break

            # Join sections when available, accounting for both explicit section
            # containers and when the body itself is a list/dict structure.
            if not candidate.get("article_markdown"):
                for section_key in ("article_sections", "sections"):
                    sections = candidate.get(section_key)
                    if not isinstance(sections, list):
                        continue
                    section_text = self._coerce_section_list(sections)
                    if section_text:
                        candidate["article_markdown"] = section_text
                        break

            article_markdown_value = candidate.get("article_markdown")
            if isinstance(article_markdown_value, list):
                coerced = self._coerce_section_list(article_markdown_value)
                if coerced:
                    candidate["article_markdown"] = coerced
            elif isinstance(article_markdown_value, dict):
                coerced = self._coerce_section_dict(article_markdown_value)
                if coerced:
                    candidate["article_markdown"] = coerced

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

        for list_key in ("highlights", "suggested_sources"):
            coerced_list = self._coerce_string_list(candidate.get(list_key))
            candidate[list_key] = coerced_list

        return candidate

    def _coerce_section_list(self, sections: list[Any]) -> str | None:
        """Convert a list of section payloads into Markdown text."""
        section_builder: list[str] = []
        for section in sections:
            if isinstance(section, str):
                text = section.strip()
                if text:
                    section_builder.append(text)
                continue

            if isinstance(section, dict):
                coerced = self._coerce_section_dict(section)
                if coerced:
                    section_builder.append(coerced)
                continue

            if isinstance(section, list):
                nested = self._coerce_section_list(section)
                if nested:
                    section_builder.append(nested)

        if not section_builder:
            return None
        return "\n\n".join(section_builder)

    def _coerce_section_dict(self, section: dict[str, Any]) -> str | None:
        """Coerce a dict-style section into Markdown."""
        if "sections" in section and isinstance(section["sections"], list):
            return self._coerce_section_list(section["sections"])

        heading = str(
            section.get("heading") or section.get("title") or section.get("section_title") or ""
        ).strip()
        body_text = section.get("markdown")
        if not body_text:
            body_text = (
                section.get("body")
                or section.get("content")
                or section.get("text")
                or section.get("paragraph")
            )
        if isinstance(body_text, list):
            body_text = self._coerce_section_list(body_text)
        else:
            body_text = str(body_text or "").strip()

        parts: list[str] = []
        if heading:
            parts.append(f"## {heading}")
        if body_text:
            parts.append(str(body_text))

        if not parts:
            return None
        return "\n\n".join(parts)

    def _coerce_string_list(self, value: Any) -> list[str]:
        """Coerce arbitrary list-like structures into a list of clean strings."""
        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                if isinstance(item, list | tuple):
                    nested = self._coerce_string_list(list(item))
                    result.extend(nested)
                    continue
                if isinstance(item, dict):
                    parts = [str(v).strip() for v in item.values() if str(v).strip()]
                    if parts:
                        result.append(" ".join(parts))
                    continue
                text = str(item).strip()
                if text:
                    result.append(text)
            return result

        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return []
            parts = [part.strip(" -•\t") for part in _STRING_LIST_SPLITTER_RE.split(cleaned)]
            return [part for part in parts if part]

        if value is None:
            return []

        text = str(value).strip()
        return [text] if text else []

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
        await self.db.async_update_request_status(req_id, "error")
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

    async def _ensure_summary_metadata(
        self,
        summary: dict[str, Any],
        req_id: int,
        content_text: str,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        """Backfill critical metadata fields when the LLM leaves them empty."""
        metadata = summary.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            summary["metadata"] = metadata

        missing_fields: set[str] = {
            field for field in self._METADATA_FIELDS if self._is_blank(metadata.get(field))
        }
        if not missing_fields:
            return summary

        firecrawl_flat = self._load_firecrawl_metadata(req_id)
        if firecrawl_flat:
            filled_from_crawl = self._apply_firecrawl_metadata(
                metadata, missing_fields, firecrawl_flat, correlation_id
            )
            missing_fields -= filled_from_crawl

        request_row: dict[str, Any] | None = None
        try:
            request_row = self.db.get_request_by_id(req_id)
        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.error("request_lookup_failed", extra={"error": str(exc), "cid": correlation_id})

        request_url: str | None = None
        if request_row:
            candidate_url = request_row.get("normalized_url") or request_row.get("input_url")
            if isinstance(candidate_url, str) and candidate_url.strip():
                request_url = candidate_url.strip()

        if "canonical_url" in missing_fields and request_url:
            metadata["canonical_url"] = request_url
            missing_fields.discard("canonical_url")
            logger.debug(
                "metadata_backfill",
                extra={"cid": correlation_id, "field": "canonical_url", "source": "request"},
            )

        if self._is_blank(metadata.get("domain")):
            domain_source = metadata.get("canonical_url") or request_url
            domain_value = self._extract_domain_from_url(domain_source)
            if domain_value:
                metadata["domain"] = domain_value
                missing_fields.discard("domain")
                logger.debug(
                    "metadata_backfill",
                    extra={"cid": correlation_id, "field": "domain", "source": "url"},
                )

        if "title" in missing_fields:
            heading_title = self._extract_heading_title(content_text)
            if heading_title:
                metadata["title"] = heading_title
                missing_fields.discard("title")
                logger.debug(
                    "metadata_backfill",
                    extra={"cid": correlation_id, "field": "title", "source": "heading"},
                )

        llm_targets = [field for field in self._LLM_METADATA_FIELDS if field in missing_fields]
        if llm_targets and content_text.strip():
            generated = await self._generate_metadata_completion(
                content_text, llm_targets, req_id, correlation_id
            )
            for key, value in generated.items():
                if value and key in missing_fields:
                    metadata[key] = value
                    missing_fields.discard(key)

        if missing_fields:
            logger.info(
                "metadata_fields_still_missing",
                extra={"cid": correlation_id, "fields": sorted(missing_fields)},
            )

        return summary

    def _apply_firecrawl_metadata(
        self,
        metadata: dict[str, Any],
        missing_fields: set[str],
        flat_metadata: dict[str, str],
        correlation_id: str | None,
    ) -> set[str]:
        """Apply Firecrawl metadata values for missing fields."""
        filled: set[str] = set()
        for field in list(missing_fields):
            for alias in self._FIRECRAWL_FIELD_ALIASES.get(field, ()):
                candidate = flat_metadata.get(alias)
                if self._is_blank(candidate):
                    continue
                metadata[field] = str(candidate).strip()
                filled.add(field)
                logger.debug(
                    "metadata_backfill",
                    extra={"cid": correlation_id, "field": field, "source": f"firecrawl:{alias}"},
                )
                break
        return filled

    def _load_firecrawl_metadata(self, req_id: int) -> dict[str, str]:
        """Load and flatten Firecrawl metadata for a request."""
        try:
            crawl_row = self.db.get_crawl_result_by_request(req_id)
        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.error("firecrawl_lookup_failed", extra={"error": str(exc)})
            return {}

        if not crawl_row:
            return {}

        parsed: Any = None
        metadata_raw = crawl_row.get("metadata_json")
        if metadata_raw:
            try:
                parsed = json.loads(metadata_raw)
            except Exception as exc:  # noqa: BLE001
                raise_if_cancelled(exc)
                logger.debug("firecrawl_metadata_parse_error", extra={"error": str(exc)})

        if parsed is None:
            raw_payload = crawl_row.get("raw_response_json")
            if raw_payload:
                try:
                    payload = json.loads(raw_payload)
                    if isinstance(payload, dict):
                        data_block = payload.get("data")
                        if isinstance(data_block, dict):
                            parsed = data_block.get("metadata") or data_block.get("meta")
                except Exception as exc:  # noqa: BLE001
                    raise_if_cancelled(exc)
                    logger.debug("firecrawl_raw_metadata_parse_error", extra={"error": str(exc)})

        if parsed is None:
            return {}

        flat: dict[str, str] = {}
        self._flatten_metadata_values(parsed, flat)
        return flat

    @classmethod
    def _flatten_metadata_values(cls, node: Any, collector: dict[str, str]) -> None:
        """Flatten nested metadata values into a single dict keyed by tag/property."""
        if node is None:
            return
        if isinstance(node, str | int | float):
            # Scalar without a key cannot be mapped reliably.
            return
        if isinstance(node, dict):
            key_hint = None
            for hint_key in ("property", "name", "itemprop", "rel", "key", "type"):
                if hint_key in node and isinstance(node[hint_key], str | int | float):
                    candidate = str(node[hint_key]).strip().lower()
                    if candidate:
                        key_hint = candidate
                        break

            value_hint = node.get("content") or node.get("value") or node.get("text")
            if key_hint and isinstance(value_hint, str | int | float):
                cleaned_value = str(value_hint).strip()
                if cleaned_value and key_hint not in collector:
                    collector[key_hint] = cleaned_value

            for key, value in node.items():
                normalized_key = str(key).strip().lower()
                if isinstance(value, str | int | float):
                    cleaned_child = str(value).strip()
                    if cleaned_child and normalized_key:
                        collector.setdefault(normalized_key, cleaned_child)
                else:
                    cls._flatten_metadata_values(value, collector)
            return

        if isinstance(node, list):
            for item in node:
                cls._flatten_metadata_values(item, collector)

    @staticmethod
    def _is_blank(value: Any) -> bool:
        """Return True when a metadata value is absent or empty."""
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        return not str(value).strip()

    @staticmethod
    def _extract_heading_title(content_text: str) -> str | None:
        """Derive a title from the first markdown heading or leading line."""
        if not content_text:
            return None
        match = re.search(r"^#{1,6}\s+(.+)$", content_text, flags=re.MULTILINE)
        if match:
            candidate = match.group(1).strip(" #\t")
            if candidate:
                return candidate

        lines = [line.strip() for line in content_text.splitlines() if line.strip()]
        if not lines:
            return None
        first_line = lines[0]
        if len(first_line) <= 140:
            return first_line
        return None

    async def _generate_metadata_completion(
        self,
        content_text: str,
        fields: list[str],
        req_id: int,
        correlation_id: str | None,
    ) -> dict[str, str]:
        """Ask the LLM to fill missing metadata fields when heuristics fail."""
        if not fields:
            return {}

        snippet = content_text[:6000].strip()
        if not snippet:
            return {}

        system_prompt = (
            "You extract article metadata and must respond with a strict JSON object. "
            "Do not add commentary. Use null when a field cannot be determined."
        )
        user_prompt = (
            "Provide the following metadata fields as JSON keys only: "
            f"{', '.join(fields)}.\n"
            "Base your answer on this article content.\n"
            "CONTENT START\n"
            f"{snippet}\n"
            "CONTENT END"
        )

        response_format = {
            "type": "json_object",
            "schema": {
                "name": "metadata_completion",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {field: {"type": ["string", "null"]} for field in fields},
                    "required": list(fields),
                },
            },
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            async with self._sem():
                llm = await self.openrouter.chat(
                    messages,
                    temperature=0.2,
                    max_tokens=512,
                    top_p=0.9,
                    request_id=req_id,
                    response_format=response_format,
                )
        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.warning(
                "metadata_completion_call_failed",
                extra={"cid": correlation_id, "error": str(exc)},
            )
            return {}

        await self._workflow.persist_llm_call(llm, req_id, correlation_id)

        if llm.status != "ok":
            logger.warning(
                "metadata_completion_failed",
                extra={"cid": correlation_id, "status": llm.status, "error": llm.error_text},
            )
            return {}

        parsed = self._parse_metadata_completion(llm.response_json, llm.response_text)
        if not isinstance(parsed, dict):
            logger.warning("metadata_completion_unparsed", extra={"cid": correlation_id})
            return {}

        cleaned: dict[str, str] = {}
        for field in fields:
            raw_value = parsed.get(field)
            if isinstance(raw_value, str) and raw_value.strip():
                cleaned[field] = raw_value.strip()

        if cleaned:
            logger.info(
                "metadata_completion_success",
                extra={"cid": correlation_id, "fields": list(cleaned.keys())},
            )

        return cleaned

    @staticmethod
    def _parse_metadata_completion(
        response_json: Any, response_text: str | None
    ) -> dict[str, Any] | None:
        """Parse metadata completion response into a dictionary."""
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
                        if isinstance(loaded, dict):
                            candidate = loaded
                    except Exception:  # noqa: BLE001
                        candidate = None
                if candidate is None:
                    content = message.get("content")
                    if isinstance(content, str):
                        candidate = extract_json(content) or None
        if candidate is None and response_text:
            candidate = extract_json(response_text) or None
        return candidate

    @staticmethod
    def _extract_domain_from_url(url_value: Any) -> str | None:
        """Extract domain from a canonical URL."""
        if not url_value:
            return None
        try:
            parsed = urlparse(str(url_value))
            netloc = parsed.netloc or ""
            if not netloc and parsed.path:
                netloc = parsed.path.split("/")[0]
            netloc = netloc.strip().lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            return netloc or None
        except Exception:  # noqa: BLE001
            return None

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
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Call OpenRouter to obtain additional researched insights for the article."""
        if not content_text.strip():
            return None

        summary_candidate = summary or self._last_summary_shaped
        if summary_candidate is None:
            try:
                row = self.db.get_summary_by_request(req_id)
                json_payload = row.get("json_payload") if row else None
                if json_payload:
                    summary_candidate = json.loads(json_payload)
            except Exception as exc:  # noqa: BLE001
                raise_if_cancelled(exc)
                logger.debug(
                    "insights_summary_load_failed",
                    extra={"cid": correlation_id, "error": str(exc)},
                )

        if summary_candidate and isinstance(summary_candidate, dict):
            insights_payload = summary_candidate.get("insights")
            if isinstance(insights_payload, dict) and self._insights_has_content(insights_payload):
                logger.info(
                    "insights_reused_from_summary",
                    extra={
                        "cid": correlation_id,
                        "request_id": req_id,
                        "source": "summary_payload",
                    },
                )
                self._last_summary_shaped = summary_candidate
                self._last_insights = insights_payload
                return insights_payload

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

                    await self._workflow.persist_llm_call(llm, req_id, correlation_id)

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
                    if not isinstance(self._last_summary_shaped, dict):
                        self._last_summary_shaped = {}
                    self._last_insights = insights
                    self._last_summary_shaped.setdefault("insights", insights)
                    return insights

            self._last_insights = None
            return None

        except Exception as exc:  # noqa: BLE001
            raise_if_cancelled(exc)
            logger.exception(
                "insights_generation_failed", extra={"cid": correlation_id, "error": str(exc)}
            )
            self._last_insights = None
            return None

    def _insights_has_content(self, payload: dict[str, Any]) -> bool:
        """Return True when the insights payload contains meaningful data."""

        for field in ("topic_overview", "caution"):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                return True

        list_fields = (
            "new_facts",
            "open_questions",
            "suggested_sources",
            "expansion_topics",
            "next_exploration",
        )
        for field in list_fields:
            items = payload.get(field)
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, str) and item.strip():
                    return True
                if isinstance(item, dict):
                    for value in item.values():
                        if isinstance(value, str) and value.strip():
                            return True
                        if value not in (None, "", [], {}):
                            return True
                elif item not in (None, "", [], {}):
                    return True

        return False

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

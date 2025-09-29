"""Refactored URL processor using modular components."""

# ruff: noqa: E501
# flake8: noqa

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from app.adapters.content.content_chunker import ContentChunker
from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.content.llm_summarizer import LLMSummarizer
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.adapters.telegram.message_persistence import MessagePersistence
from app.config import AppConfig
from app.core.lang import choose_language
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.database import Database
from app.db.user_interactions import async_safe_update_user_interaction

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"


@lru_cache(maxsize=4)
def _get_system_prompt(lang: str) -> str:
    """Load and cache the system prompt for the given language."""
    fname = "summary_system_ru.txt" if lang == "ru" else "summary_system_en.txt"
    path = _PROMPT_DIR / fname
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return "You are a precise assistant that returns only a strict JSON object matching the provided schema."


class URLProcessor:
    """Refactored URL processor using modular components."""

    def __init__(
        self,
        cfg: AppConfig,
        db: Database,
        firecrawl: FirecrawlClient,
        openrouter: OpenRouterClient,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.response_formatter = response_formatter
        self._audit = audit_func

        # Initialize modular components
        self.content_extractor = ContentExtractor(
            cfg=cfg,
            db=db,
            firecrawl=firecrawl,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.content_chunker = ContentChunker(
            cfg=cfg,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.llm_summarizer = LLMSummarizer(
            cfg=cfg,
            db=db,
            openrouter=openrouter,
            response_formatter=response_formatter,
            audit_func=audit_func,
            sem=sem,
        )

        self.message_persistence = MessagePersistence(db=db)

    async def handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
        silent: bool = False,
    ) -> None:
        """Handle complete URL processing flow from extraction to summarization.

        Args:
            silent: If True, suppress all Telegram responses and only persist to database
        """
        if await self._maybe_reply_with_cached_summary(
            message,
            url_text,
            correlation_id=correlation_id,
            interaction_id=interaction_id,
            silent=silent,
        ):
            return

        try:
            # Extract and process content
            (
                req_id,
                content_text,
                content_source,
                detected,
            ) = await self.content_extractor.extract_and_process_content(
                message, url_text, correlation_id, interaction_id, silent
            )

            # Choose language and load system prompt
            chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)
            system_prompt = await self._load_system_prompt(chosen_lang)

            logger.debug(
                "language_choice",
                extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
            )

            # Notify: language detected with content preview (skip if silent)
            if not silent:
                content_preview = (
                    content_text[:150] + "..." if len(content_text) > 150 else content_text
                )
                await self.response_formatter.send_language_detection_notification(
                    message, detected, content_preview, silent=silent
                )

            # Check if content should be chunked
            should_chunk, max_chars, chunks = self.content_chunker.should_chunk_content(
                content_text, chosen_lang
            )

            if should_chunk and self.cfg.openrouter.long_context_model:
                logger.info(
                    "chunking_bypassed_long_context",
                    extra={
                        "cid": correlation_id,
                        "long_context_model": self.cfg.openrouter.long_context_model,
                        "content_length": len(content_text),
                    },
                )
                should_chunk = False
                chunks = None

            # Inform the user how the content will be handled (skip if silent)
            await self.response_formatter.send_content_analysis_notification(
                message,
                len(content_text),
                max_chars,
                should_chunk,
                chunks,
                self.cfg.openrouter.structured_output_mode,
                silent=silent,
            )

            logger.info(
                "content_handling",
                extra={
                    "cid": correlation_id,
                    "length": len(content_text),
                    "enable_chunking": should_chunk,
                    "threshold": max_chars,
                    "chunks": len(chunks or []) if should_chunk else 1,
                    "structured_output_enabled": self.cfg.openrouter.enable_structured_outputs,
                    "structured_output_mode": self.cfg.openrouter.structured_output_mode,
                },
            )

            # Process content based on chunking decision
            if should_chunk and chunks and len(chunks) > 1:
                # Process chunks and aggregate
                shaped = await self.content_chunker.process_chunks(
                    chunks, system_prompt, chosen_lang, req_id, correlation_id
                )

                if shaped:
                    # Create stub LLM result for consistency
                    llm = self._create_chunk_llm_stub()

                    # Persist and respond (skip Telegram responses if silent)
                    await self._persist_and_respond_chunked(
                        message,
                        req_id,
                        chosen_lang,
                        shaped,
                        llm,
                        len(chunks),
                        correlation_id,
                        interaction_id,
                        silent=silent,
                    )
                    # Generate insights even in silent mode (for batch processing)
                    await self._handle_additional_insights(
                        message,
                        content_text,
                        chosen_lang,
                        req_id,
                        correlation_id,
                        summary=shaped,
                        silent=silent,
                    )
                    return
                else:
                    # Fallback to single-pass if chunking failed
                    logger.warning(
                        "chunking_failed_fallback_to_single", extra={"cid": correlation_id}
                    )

            # Single-pass summarization
            shaped = await self.llm_summarizer.summarize_content(
                message,
                content_text,
                chosen_lang,
                system_prompt,
                req_id,
                max_chars,
                correlation_id,
                interaction_id,
                silent=silent,
            )

            if shaped:
                llm_result = self.llm_summarizer.last_llm_result

                # Skip Telegram responses if silent
                if not silent:
                    await self.response_formatter.send_structured_summary_response(
                        message,
                        shaped,
                        llm_result,
                    )
                    logger.info(
                        "reply_json_sent", extra={"cid": correlation_id, "request_id": req_id}
                    )

                    # Notify user that we will attempt to generate extra research insights
                    try:
                        await self.response_formatter.safe_reply(
                            message,
                            "🧠 Generating additional research insights…",
                        )
                    except Exception:
                        pass

                    await self._handle_additional_insights(
                        message,
                        content_text,
                        chosen_lang,
                        req_id,
                        correlation_id,
                        summary=shaped,
                    )

                    # Generate a standalone custom article based on extracted topics/tags
                    try:
                        topics = shaped.get("key_ideas") or []
                        tags = shaped.get("topic_tags") or []
                        if (topics or tags) and isinstance(topics, list) and isinstance(tags, list):
                            await self.response_formatter.safe_reply(
                                message,
                                "📝 Crafting a standalone article from topics & tags…",
                            )
                            article = await self.llm_summarizer.generate_custom_article(
                                message,
                                chosen_lang=chosen_lang,
                                req_id=req_id,
                                topics=[str(x) for x in topics if str(x).strip()],
                                tags=[str(x) for x in tags if str(x).strip()],
                                correlation_id=correlation_id,
                            )
                            if article:
                                await self.response_formatter.send_custom_article(message, article)
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "custom_article_flow_error",
                            extra={"cid": correlation_id, "error": str(exc)},
                        )
                else:
                    # Silent mode: persist and generate insights without responses
                    new_version = await self.db.async_upsert_summary(
                        request_id=req_id,
                        lang=chosen_lang,
                        json_payload=shaped,
                        is_read=False,
                    )
                    await self.db.async_update_request_status(req_id, "ok")
                    self._audit(
                        "INFO", "summary_upserted", {"request_id": req_id, "version": new_version}
                    )

                    # Generate insights even in silent mode (for batch processing)
                    await self._handle_additional_insights(
                        message,
                        content_text,
                        chosen_lang,
                        req_id,
                        correlation_id,
                        summary=shaped,
                        silent=True,
                    )
                    logger.info(
                        "silent_summary_persisted",
                        extra={"cid": correlation_id, "request_id": req_id},
                    )

        except ValueError as e:
            # Handle known errors (like Firecrawl failures)
            logger.error("url_flow_error", extra={"error": str(e), "cid": correlation_id})
        except Exception as e:
            # Handle unexpected errors
            logger.exception(
                "url_flow_unexpected_error", extra={"error": str(e), "cid": correlation_id}
            )

    def _create_chunk_llm_stub(self) -> Any:
        """Create a stub LLM result for chunked processing."""
        return type(
            "LLMStub",
            (),
            {
                "status": "ok",
                "latency_ms": None,
                "model": self.cfg.openrouter.model,
                "cost_usd": None,
                "tokens_prompt": None,
                "tokens_completion": None,
                "structured_output_used": True,
                "structured_output_mode": self.cfg.openrouter.structured_output_mode,
            },
        )()

    async def _persist_and_respond_chunked(
        self,
        message: Any,
        req_id: int,
        chosen_lang: str,
        shaped: dict[str, Any],
        llm: Any,
        chunk_count: int,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> None:
        """Persist chunked results and send response."""
        try:
            new_version = await self.db.async_upsert_summary(
                request_id=req_id,
                lang=chosen_lang,
                json_payload=shaped,
                is_read=not silent,
            )
            await self.db.async_update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as e:  # noqa: BLE001
            logger.error("persist_summary_error", extra={"error": str(e), "cid": correlation_id})

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
                logger_=logger,
            )

        # Send structured results (skip if silent)
        if not silent:
            await self.response_formatter.send_structured_summary_response(
                message, shaped, llm, chunks=chunk_count
            )
            logger.info("reply_json_sent", extra={"cid": correlation_id, "request_id": req_id})

    async def _handle_additional_insights(
        self,
        message: Any,
        content_text: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
        *,
        summary: dict[str, Any] | None = None,
        silent: bool = False,
    ) -> None:
        """Generate and persist additional insights using the LLM."""
        logger.info(
            "insights_flow_started",
            extra={"cid": correlation_id, "content_len": len(content_text), "lang": chosen_lang},
        )

        try:
            insights = await self.llm_summarizer.generate_additional_insights(
                message,
                content_text=content_text,
                chosen_lang=chosen_lang,
                req_id=req_id,
                correlation_id=correlation_id,
                summary=summary,
            )

            if insights:
                logger.info(
                    "insights_generated_successfully",
                    extra={
                        "cid": correlation_id,
                        "facts_count": len(insights.get("new_facts", [])),
                        "has_overview": bool(insights.get("topic_overview")),
                    },
                )

                # Only send insights message if not in silent mode
                if not silent:
                    await self.response_formatter.send_additional_insights_message(
                        message, insights, correlation_id
                    )
                    logger.info("insights_message_sent", extra={"cid": correlation_id})
                else:
                    logger.info("insights_generated_silently", extra={"cid": correlation_id})

                try:
                    self.db.update_summary_insights(req_id, insights)
                    logger.debug(
                        "insights_persisted", extra={"cid": correlation_id, "request_id": req_id}
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "persist_insights_error",
                        extra={"cid": correlation_id, "error": str(exc)},
                    )
            else:
                logger.warning(
                    "insights_generation_returned_empty",
                    extra={"cid": correlation_id, "reason": "LLM returned None or empty insights"},
                )

        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "insights_flow_error",
                extra={"cid": correlation_id, "error": str(exc)},
            )

    async def _load_system_prompt(self, lang: str) -> str:
        """Load system prompt file based on language."""
        return _get_system_prompt(lang)

    def _is_summary_complete(self, summary: dict[str, Any]) -> bool:
        """Check if a summary has the essential fields populated."""
        if not isinstance(summary, dict):
            return False

        # Essential fields that must be present and non-empty
        essential_fields = [
            ("summary_250", "summary_250"),
            ("summary_1000", "summary_1000"),
            ("tldr", "tldr"),
        ]

        # Check essential fields
        for field, lookup in essential_fields:
            value = summary.get(lookup)
            if lookup == "summary_1000" and not value:
                value = summary.get("tldr")
            if lookup == "tldr" and not value:
                value = summary.get("summary_1000")
            if not value or not str(value).strip():
                return False

        # At least one of these should have content
        content_fields = [
            "key_ideas",
            "topic_tags",
            "entities",
        ]

        has_content = False
        for field in content_fields:
            value = summary.get(field)
            if field == "entities":
                if isinstance(value, dict) and any(
                    isinstance(v, list) and len(v) > 0 for v in value.values()
                ):
                    has_content = True
                    break
            elif isinstance(value, list) and len(value) > 0:
                has_content = True
                break

        if not has_content:
            logger.debug(
                "cached_summary_missing_optional_content",
                extra={"missing_fields": content_fields},
            )

        return True

    def _get_missing_summary_fields(self, summary: dict[str, Any]) -> list[str]:
        """Get list of missing or empty essential fields."""
        if not isinstance(summary, dict):
            return ["invalid_summary_format"]

        missing = []
        essential_fields = [
            ("summary_250", "summary_250"),
            ("summary_1000", "summary_1000"),
            ("tldr", "tldr"),
        ]

        for field, lookup in essential_fields:
            value = summary.get(lookup)
            if lookup == "summary_1000" and not value:
                value = summary.get("tldr")
            if lookup == "tldr" and not value:
                value = summary.get("summary_1000")
            if not value or not str(value).strip():
                missing.append(field)

        return missing

    async def _maybe_reply_with_cached_summary(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None,
        interaction_id: int | None,
        silent: bool = False,
    ) -> bool:
        """Return True if an existing summary was reused."""
        try:
            norm = normalize_url(url_text)
        except Exception:
            return False

        dedupe = url_hash_sha256(norm)
        existing_req = await self.db.async_get_request_by_dedupe_hash(dedupe)
        if not isinstance(existing_req, Mapping):
            getter = getattr(self.db, "get_request_by_dedupe_hash", None)
            existing_req = getter(dedupe) if callable(getter) else None

        if isinstance(existing_req, Mapping):
            existing_req = dict(existing_req)

        if not existing_req:
            return False

        req_id = int(existing_req["id"])
        summary_row = await self.db.async_get_summary_by_request(req_id)
        if not isinstance(summary_row, Mapping):
            getter = getattr(self.db, "get_summary_by_request", None)
            summary_row = getter(req_id) if callable(getter) else None

        if isinstance(summary_row, Mapping):
            summary_row = dict(summary_row)

        if not summary_row:
            return False

        payload = summary_row.get("json_payload")
        if payload is None:
            logger.debug(
                "cached_summary_empty_payload",
                extra={"request_id": req_id, "cid": correlation_id},
            )
            return False

        if isinstance(payload, Mapping):
            shaped = dict(payload)
        elif isinstance(payload, str):
            try:
                shaped = json.loads(payload)
            except json.JSONDecodeError:
                logger.warning(
                    "cached_summary_decode_failed",
                    extra={"request_id": req_id, "cid": correlation_id},
                )
                return False
        else:
            logger.warning(
                "cached_summary_unsupported_payload",
                extra={"request_id": req_id, "cid": correlation_id, "type": type(payload).__name__},
            )
            return False

        # Validate that the summary is complete and has essential fields
        if not self._is_summary_complete(shaped):
            logger.debug(
                "cached_summary_incomplete",
                extra={
                    "request_id": req_id,
                    "cid": correlation_id,
                    "missing_fields": self._get_missing_summary_fields(shaped),
                },
            )
            return False

        if correlation_id:
            try:
                self.db.update_request_correlation_id(req_id, correlation_id)
            except Exception as exc:  # noqa: BLE001
                logger.error("persist_cid_error", extra={"error": str(exc), "cid": correlation_id})

        # Skip Telegram responses if silent
        if not silent:
            await self.response_formatter.send_url_accepted_notification(
                message, norm, correlation_id or "", silent=silent
            )
            await self.response_formatter.send_cached_summary_notification(message, silent=silent)
            # Resolve model used previously for this request and pass a stub to avoid 'unknown'
            try:
                model_name = self.db.get_latest_llm_model_by_request_id(req_id)
            except Exception:
                model_name = None
            llm_stub = type("LLMStub", (), {"model": model_name})()
            await self.response_formatter.send_structured_summary_response(
                message, shaped, llm_stub
            )

            insights_raw = summary_row.get("insights_json")
            insights_payload: dict[str, Any] | None
            if isinstance(insights_raw, Mapping):
                insights_payload = dict(cast(Mapping[str, Any], insights_raw))
            elif isinstance(insights_raw, str) and insights_raw.strip():
                try:
                    decoded = json.loads(insights_raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "cached_insights_decode_failed",
                        extra={"request_id": req_id, "cid": correlation_id},
                    )
                    decoded = None
                if isinstance(decoded, Mapping):
                    insights_payload = dict(cast(Mapping[str, Any], decoded))
                else:
                    insights_payload = None
            else:
                insights_payload = None
            if insights_payload:
                await self.response_formatter.send_additional_insights_message(
                    message, dict(insights_payload), correlation_id
                )

        await self.db.async_update_request_status(req_id, "ok")

        self._audit(
            "INFO",
            "summary_cache_hit",
            {
                "request_id": req_id,
                "url": norm,
                "cid": correlation_id,
            },
        )

        if interaction_id:
            await async_safe_update_user_interaction(
                self.db,
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
                logger_=logger,
            )

        logger.info(
            "summary_cache_reused",
            extra={"request_id": req_id, "cid": correlation_id, "normalized_url": norm},
        )
        return True

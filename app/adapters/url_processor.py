# ruff: noqa: E501
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Callable

from app.adapters.firecrawl_parser import FirecrawlClient, FirecrawlResult
from app.adapters.openrouter_client import OpenRouterClient
from app.config import AppConfig
from app.core.html_utils import (
    chunk_sentences,
    clean_markdown_article_text,
    html_to_text,
    normalize_with_textacy,
    split_sentences,
)
from app.core.json_utils import extract_json
from app.core.lang import LANG_RU, choose_language, detect_language
from app.core.summary_aggregate import aggregate_chunk_summaries
from app.core.summary_contract import validate_and_shape_summary
from app.core.url_utils import normalize_url, url_hash_sha256
from app.db.database import Database
from app.utils.json_validation import parse_summary_response

if TYPE_CHECKING:
    from app.adapters.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)

# Route versioning constants
URL_ROUTE_VERSION = 1


class URLProcessor:
    """Handles URL-based content processing including Firecrawl extraction and AI summarization."""

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
        self.firecrawl = firecrawl
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem

    async def handle_url_flow(
        self,
        message: Any,
        url_text: str,
        *,
        correlation_id: str | None = None,
        interaction_id: int | None = None,
    ) -> None:
        """Handle complete URL processing flow from extraction to summarization."""
        # Declare crawl variable for type checking
        crawl: FirecrawlResult | MockCrawl

        norm = normalize_url(url_text)
        dedupe = url_hash_sha256(norm)
        logger.info(
            "url_flow_detected",
            extra={"url": url_text, "normalized": norm,
                   "hash": dedupe, "cid": correlation_id},
        )

        # Notify: request accepted with URL preview
        await self.response_formatter.send_url_accepted_notification(message, norm, correlation_id)

        # Dedupe check
        existing_req = self.db.get_request_by_dedupe_hash(dedupe)
        req_id: int  # Initialize variable for type checker
        if existing_req:
            req_id = int(existing_req["id"])  # reuse existing request
            self._audit(
                "INFO",
                "url_dedupe_hit",
                {"request_id": req_id, "hash": dedupe,
                    "url": url_text, "cid": correlation_id},
            )
            if correlation_id:
                try:
                    self.db.update_request_correlation_id(
                        req_id, correlation_id)
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "persist_cid_error", extra={"error": str(e), "cid": correlation_id}
                    )
        else:
            # Create request row (pending)
            chat_obj = getattr(message, "chat", None)
            chat_id_raw = getattr(
                chat_obj, "id", 0) if chat_obj is not None else None
            chat_id = int(chat_id_raw) if chat_id_raw is not None else None

            from_user_obj = getattr(message, "from_user", None)
            user_id_raw = getattr(from_user_obj, "id",
                                  0) if from_user_obj is not None else None
            user_id = int(user_id_raw) if user_id_raw is not None else None

            msg_id_raw = getattr(
                message, "id", getattr(message, "message_id", 0))
            input_message_id = int(
                msg_id_raw) if msg_id_raw is not None else None

            req_id = self.db.create_request(
                type_="url",
                status="pending",
                correlation_id=correlation_id,
                chat_id=chat_id,
                user_id=user_id,
                input_url=url_text,
                normalized_url=norm,
                dedupe_hash=dedupe,
                input_message_id=input_message_id,
                route_version=URL_ROUTE_VERSION,
            )

            # Snapshot telegram message (only on first request for this URL)
            try:
                self._persist_message_snapshot(req_id, message)
            except Exception as e:  # noqa: BLE001
                logger.error("snapshot_error", extra={
                             "error": str(e), "cid": correlation_id})

        # Note: We don't reuse summaries here to allow version increment on dedupe
        # The request is deduped (reused), but summaries are always regenerated

        # Firecrawl or reuse existing crawl result
        existing_crawl = self.db.get_crawl_result_by_request(req_id)
        if existing_crawl and (
            existing_crawl.get(
                "content_markdown") or existing_crawl.get("content_html")
        ):
            md = existing_crawl.get("content_markdown")
            html = existing_crawl.get("content_html")

            # Process content with HTML fallback for empty markdown
            if md and md.strip():
                content_text = clean_markdown_article_text(md)
                content_source = "markdown"
            elif html and html.strip():
                content_text = html_to_text(html)
                content_source = "html"
                logger.info(
                    "html_fallback_used_existing",
                    extra={
                        "cid": correlation_id,
                        "reason": "markdown_empty_or_missing",
                        "html_len": len(html),
                        "cleaned_text_len": len(content_text),
                    },
                )
            else:
                content_text = ""
                content_source = "none"
            # Optional normalization (feature-flagged)
            try:
                if getattr(self.cfg.runtime, "enable_textacy", False):
                    content_text = normalize_with_textacy(content_text)
            except Exception:
                pass
            self._audit("INFO", "reuse_crawl_result", {
                        "request_id": req_id, "cid": correlation_id})
            await self.response_formatter.send_content_reuse_notification(message)

            # Create a mock crawl object for consistency with the else branch
            crawl = MockCrawl(md, html)
        else:
            # Notify: starting Firecrawl with progress indicator
            await self.response_formatter.send_firecrawl_start_notification(message)
            async with self._sem():
                crawl = await self.firecrawl.scrape_markdown(url_text, request_id=req_id)
            try:
                self.db.insert_crawl_result(
                    request_id=req_id,
                    source_url=crawl.source_url,
                    endpoint=crawl.endpoint,
                    http_status=crawl.http_status,
                    status=crawl.status,
                    options_json=json.dumps(crawl.options_json or {}),
                    content_markdown=crawl.content_markdown,
                    content_html=crawl.content_html,
                    structured_json=json.dumps(crawl.structured_json or {}),
                    metadata_json=json.dumps(crawl.metadata_json or {}),
                    links_json=json.dumps(crawl.links_json or {}),
                    screenshots_paths_json=None,
                    raw_response_json=json.dumps(
                        crawl.raw_response_json or {}),
                    latency_ms=crawl.latency_ms,
                    error_text=crawl.error_text,
                )
            except Exception as e:  # noqa: BLE001
                logger.error("persist_crawl_error", extra={
                             "error": str(e), "cid": correlation_id})

            # Debug logging for crawl result
            logger.debug(
                "crawl_result_debug",
                extra={
                    "cid": correlation_id,
                    "status": crawl.status,
                    "http_status": crawl.http_status,
                    "error_text": crawl.error_text,
                    "has_markdown": bool(crawl.content_markdown),
                    "has_html": bool(crawl.content_html),
                    "markdown_len": len(crawl.content_markdown) if crawl.content_markdown else 0,
                    "html_len": len(crawl.content_html) if crawl.content_html else 0,
                },
            )

            # Check if we have any usable content
            has_markdown = bool(
                crawl.content_markdown and crawl.content_markdown.strip())
            has_html = bool(crawl.content_html and crawl.content_html.strip())

            if crawl.status != "ok" or not (has_markdown or has_html):
                self.db.update_request_status(req_id, "error")
                await self.response_formatter.send_error_notification(
                    message, "firecrawl_error", correlation_id
                )
                logger.error(
                    "firecrawl_error",
                    extra={
                        "error": crawl.error_text,
                        "cid": correlation_id,
                        "status": crawl.status,
                        "http_status": crawl.http_status,
                        "has_markdown": has_markdown,
                        "has_html": has_html,
                    },
                )
                try:
                    self._audit(
                        "ERROR",
                        "firecrawl_error",
                        {"request_id": req_id, "cid": correlation_id,
                            "error": crawl.error_text},
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
                        error_message=f"Firecrawl error: {crawl.error_text or 'Unknown error'}",
                        request_id=req_id,
                    )
                return

            # Notify: Firecrawl success
            excerpt_len = (len(crawl.content_markdown) if crawl.content_markdown else 0) or (
                len(crawl.content_html) if crawl.content_html else 0
            )
            latency_sec = (crawl.latency_ms or 0) / 1000.0
            await self.response_formatter.send_firecrawl_success_notification(
                message, excerpt_len, latency_sec
            )

            # Process content with HTML fallback for empty markdown
            if crawl.content_markdown and crawl.content_markdown.strip():
                content_text = clean_markdown_article_text(
                    crawl.content_markdown)
                content_source = "markdown"
            elif crawl.content_html and crawl.content_html.strip():
                content_text = html_to_text(crawl.content_html)
                content_source = "html"
                logger.info(
                    "html_fallback_used",
                    extra={
                        "cid": correlation_id,
                        "reason": "markdown_empty_or_missing",
                        "html_len": len(crawl.content_html),
                        "cleaned_text_len": len(content_text),
                    },
                )
                # Notify user that HTML fallback was used
                await self.response_formatter.send_html_fallback_notification(
                    message, len(content_text)
                )
            else:
                # This should not happen due to validation above, but handle gracefully
                content_text = ""
                content_source = "none"
                logger.error(
                    "no_content_available",
                    extra={
                        "cid": correlation_id,
                        "markdown_len": len(crawl.content_markdown)
                        if crawl.content_markdown
                        else 0,
                        "html_len": len(crawl.content_html) if crawl.content_html else 0,
                    },
                )
            # Optional normalization (feature-flagged)
            try:
                if getattr(self.cfg.runtime, "enable_textacy", False):
                    content_text = normalize_with_textacy(content_text)
            except Exception:
                pass

        # Language detection and choice
        detected = detect_language(content_text or "")
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

        # Notify: language detected with content preview
        content_preview = content_text[:150] + \
            "..." if len(content_text) > 150 else content_text
        await self.response_formatter.send_language_detection_notification(
            message, detected, content_preview
        )

        # LLM - chunk long content (map-only with aggregation)
        # Be defensive against MagicMock configs in tests: only honor proper types
        _enable_chunking_val = getattr(
            self.cfg.runtime, "enable_chunking", False)
        enable_chunking = _enable_chunking_val if isinstance(
            _enable_chunking_val, bool) else False
        _max_chars_val = getattr(self.cfg.runtime, "chunk_max_chars", 200000)
        configured_max = _max_chars_val if isinstance(
            _max_chars_val, int) else 200000
        # Choose model to estimate context threshold: prefer long_context_model if configured and string
        _lc_model = getattr(self.cfg.openrouter, "long_context_model", None)
        _primary_model = getattr(self.cfg.openrouter, "model", "")
        threshold_model = (
            _lc_model
            if isinstance(_lc_model, str) and _lc_model
            else (_primary_model if isinstance(_primary_model, str) else "")
        )
        max_chars = self._estimate_max_chars_for_model(
            threshold_model, configured_max)
        content_len = len(content_text)
        text_for_summary = content_text
        chunks: list[str] | None = None
        if enable_chunking and content_len > max_chars:
            logger.info(
                "chunking_enabled",
                extra={
                    "cid": correlation_id,
                    "configured_max": configured_max,
                    "adaptive_max": max_chars,
                    "model_for_threshold": threshold_model,
                },
            )
            try:
                sentences = split_sentences(
                    content_text, "ru" if chosen_lang == LANG_RU else "en")
                chunks = chunk_sentences(sentences, max_chars=2000)
            except Exception:
                chunks = None

        # Inform the user how the content will be handled
        await self.response_formatter.send_content_analysis_notification(
            message,
            content_len,
            max_chars,
            enable_chunking,
            chunks,
            self.cfg.openrouter.structured_output_mode,
        )

        logger.info(
            "content_handling",
            extra={
                "cid": correlation_id,
                "length": content_len,
                "enable_chunking": enable_chunking,
                "threshold": max_chars,
                "chunks": (len(chunks or []) if enable_chunking and content_len > max_chars else 1),
                "structured_output_enabled": self.cfg.openrouter.enable_structured_outputs,
                "structured_output_mode": self.cfg.openrouter.structured_output_mode,
            },
        )

        if chunks and len(chunks) > 1:
            # Map-only: get structured summaries per chunk and aggregate deterministically
            chunk_summaries: list[dict[str, Any]] = []
            for idx, chunk in enumerate(chunks, start=1):
                messages = [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": (
                            f"Analyze this part {idx}/{len(chunks)} and output ONLY a valid JSON object matching the schema. "
                            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n"
                            f"CONTENT START\n{chunk}\nCONTENT END"
                        ),
                    },
                ]
                async with self._sem():
                    # Use enhanced structured output format
                    response_format_cf = self._build_structured_response_format()
                    resp = await self.openrouter.chat(
                        messages,
                        temperature=self.cfg.openrouter.temperature,
                        max_tokens=self.cfg.openrouter.max_tokens,
                        top_p=self.cfg.openrouter.top_p,
                        request_id=req_id,
                        response_format=response_format_cf,
                    )
                if resp.status == "ok":
                    # Prefer parsed payload
                    parsed: dict[str, Any] | None = None
                    try:
                        if resp.response_json and isinstance(resp.response_json, dict):
                            ch = resp.response_json.get("choices") or []
                            if ch and isinstance(ch[0], dict):
                                msg0 = ch[0].get("message") or {}
                                p = msg0.get("parsed")
                                if p is not None:
                                    parsed = p if isinstance(p, dict) else None
                    except Exception:
                        parsed = None
                    try:
                        if parsed is None and (resp.response_text or "").strip():
                            parsed = json.loads(
                                (resp.response_text or "").strip().strip("` "))
                    except Exception:
                        parsed = None
                    if parsed is not None:
                        try:
                            shaped_chunk = validate_and_shape_summary(parsed)
                            chunk_summaries.append(shaped_chunk)
                        except Exception:
                            pass
            # Aggregate chunk summaries into final
            if chunk_summaries:
                aggregated = aggregate_chunk_summaries(chunk_summaries)
                shaped = validate_and_shape_summary(aggregated)
                # Short-circuit the rest of the flow; persist and reply below
                llm = type(
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
                # Persist and respond using shaped
                try:
                    new_version = self.db.upsert_summary(
                        request_id=req_id, lang=chosen_lang, json_payload=json.dumps(
                            shaped)
                    )
                    self.db.update_request_status(req_id, "ok")
                    self._audit(
                        "INFO", "summary_upserted", {
                            "request_id": req_id, "version": new_version}
                    )
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "persist_summary_error", extra={"error": str(e), "cid": correlation_id}
                    )

                if interaction_id:
                    self._update_user_interaction(
                        interaction_id=interaction_id,
                        response_sent=True,
                        response_type="summary",
                        request_id=req_id,
                    )

                # Send enhanced results
                await self.response_formatter.send_enhanced_summary_response(
                    message, shaped, llm, chunks=len(chunks)
                )
                logger.info("reply_json_sent", extra={
                            "cid": correlation_id, "request_id": req_id})
                return

        # Validate content before sending to LLM
        if not text_for_summary or not text_for_summary.strip():
            logger.error(
                "empty_content_for_llm",
                extra={
                    "cid": correlation_id,
                    "content_source": content_source,
                    "original_markdown_len": len(crawl.content_markdown)
                    if crawl.content_markdown
                    else 0,
                    "original_html_len": len(crawl.content_html) if crawl.content_html else 0,
                    "processed_content_len": len(content_text),
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
            return

        user_content = (
            f"Analyze the following content and output ONLY a valid JSON object that matches the system contract exactly. "
            f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}. Do NOT include any text outside the JSON.\n\n"
            f"CONTENT START\n{text_for_summary}\nCONTENT END"
        )

        logger.info(
            "llm_content_validation",
            extra={
                "cid": correlation_id,
                "system_prompt_len": len(system_prompt),
                "user_content_len": len(user_content),
                "text_for_summary_len": len(text_for_summary),
                "text_preview": (
                    text_for_summary[:200] + "..."
                    if len(text_for_summary) > 200
                    else text_for_summary
                ),
                "has_content": bool(text_for_summary.strip()),
                "content_source": content_source,
                "structured_output_config": {
                    "enabled": self.cfg.openrouter.enable_structured_outputs,
                    "mode": self.cfg.openrouter.structured_output_mode,
                    "require_parameters": self.cfg.openrouter.require_parameters,
                    "auto_fallback": self.cfg.openrouter.auto_fallback_structured,
                },
            },
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        # Notify: Starting enhanced LLM call
        await self.response_formatter.send_llm_start_notification(
            message,
            self.cfg.openrouter.model,
            len(text_for_summary),
            self.cfg.openrouter.structured_output_mode,
        )

        # If we have a long-context model configured and content exceeds threshold,
        # prefer a single-pass summary using that model (avoids chunking multi-calls).
        model_override = None
        if content_len > max_chars and (self.cfg.openrouter.long_context_model or ""):
            model_override = self.cfg.openrouter.long_context_model

        async with self._sem():
            # Use enhanced structured output configuration
            response_format = self._build_structured_response_format()

            llm = await self.openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=(self.cfg.openrouter.max_tokens or 2048),
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
                response_format=response_format,
                model_override=model_override,
            )

        # Enhanced LLM completion notification
        await self.response_formatter.send_llm_completion_notification(message, llm, correlation_id)

        # Enhanced error handling and salvage logic
        salvage_shaped: dict[str, Any] | None = None
        if llm.status != "ok" and (llm.error_text or "") == "structured_output_parse_error":
            try:
                # Try robust local parsing first
                parsed = extract_json(llm.response_text or "")
                if isinstance(parsed, dict):
                    salvage_shaped = validate_and_shape_summary(parsed)
                if salvage_shaped is None:
                    pr = parse_summary_response(
                        llm.response_json, llm.response_text)
                    salvage_shaped = pr.shaped

                if salvage_shaped:
                    logger.info("structured_output_salvage_success",
                                extra={"cid": correlation_id})
            except Exception as e:
                logger.error("salvage_error", extra={
                             "error": str(e), "cid": correlation_id})
                salvage_shaped = None

        # Async optimization: Run database operations concurrently with response processing
        async def _persist_llm_call():
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

        # Start database persistence in background
        # Fire and forget for performance
        asyncio.create_task(_persist_llm_call())

        if llm.status != "ok" and salvage_shaped is None:
            # Allow JSON repair flow for structured_output_parse_error instead of returning early
            if (llm.error_text or "") != "structured_output_parse_error":
                self.db.update_request_status(req_id, "error")
                # Detailed error message already sent above, just log for debugging
                logger.error(
                    "openrouter_error", extra={"error": llm.error_text, "cid": correlation_id}
                )
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

        # Enhanced parsing with better error handling
        summary_shaped: dict[str, Any] | None = salvage_shaped

        if summary_shaped is None:
            parse_result = parse_summary_response(
                llm.response_json, llm.response_text)
            if parse_result and parse_result.shaped is not None:
                summary_shaped = parse_result.shaped
                if parse_result.used_local_fix:
                    logger.info(
                        "json_local_fix_applied",
                        extra={"cid": correlation_id, "stage": "initial"},
                    )
            else:
                # Enhanced repair logic with structured outputs
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
                            max_tokens=(
                                self.cfg.openrouter.max_tokens or 2048),
                            top_p=self.cfg.openrouter.top_p,
                            request_id=req_id,
                            response_format=repair_response_format,
                        )
                    if repair.status == "ok":
                        repair_result = parse_summary_response(
                            repair.response_json, repair.response_text
                        )
                        if repair_result.shaped is not None:
                            summary_shaped = repair_result.shaped
                            logger.info(
                                "json_repair_success_enhanced",
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

        if summary_shaped is None:
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

        # Enhanced logging with structured output details
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

        try:
            new_version = self.db.upsert_summary(
                request_id=req_id, lang=chosen_lang, json_payload=json.dumps(
                    summary_shaped)
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

        # Send enhanced summary response
        await self.response_formatter.send_enhanced_summary_response(message, summary_shaped, llm)
        logger.info("reply_json_sent", extra={
                    "cid": correlation_id, "request_id": req_id})

    def _estimate_max_chars_for_model(self, model_name: str | None, base_default: int) -> int:
        """Return an adaptive chunk threshold based on concrete context limits.

        Uses token capacities provided for specific families and converts to characters
        via a 4 chars/token heuristic, with a 0.75 safety factor.
        Defaults to the configured base_default when unknown.
        """
        try:
            if not model_name:
                return int(base_default)
            name = model_name.lower()

            # Helper to convert tokens->chars with 0.75 safety factor
            def tok(tokens: int) -> int:
                return int(tokens * 4 * 0.75)

            # Explicit capacities (user-provided):
            # - GPT-5: 400,000 tokens
            # - GPT-4o: 128,000 tokens
            # - Gemini 2.5 Pro: 1,000,000 tokens
            if "gpt-5" in name:
                return max(base_default, tok(400_000))  # ≈ 1,200,000 chars
            if "gpt-4o" in name:
                return max(base_default, tok(128_000))  # ≈ 384,000 chars
            if "gemini-2.5" in name or "2.5-pro" in name or "gemini-2-5" in name:
                return max(base_default, tok(1_000_000))  # ≈ 3,000,000 chars

            # Other generous defaults for known large-context families
            # No other families used in this deployment

            # fallback
            return int(base_default)
        except Exception:
            return int(base_default)

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


class MockCrawl:
    """Mock crawl object for reused content."""

    def __init__(self, markdown: str | None, html: str | None):
        self.status = "ok"
        self.http_status = 200
        self.content_markdown = markdown
        self.content_html = html
        self.structured_json = None
        self.metadata_json = None
        self.links_json = None
        self.raw_response_json = None
        self.latency_ms = None
        self.error_text = None
        self.source_url = None
        self.endpoint = "/v1/scrape"
        self.options_json = None
        self.correlation_id = None

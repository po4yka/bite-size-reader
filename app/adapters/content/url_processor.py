"""Refactored URL processor using modular components."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.adapters.content.content_chunker import ContentChunker
from app.adapters.content.content_extractor import ContentExtractor
from app.adapters.content.llm_summarizer import LLMSummarizer
from app.adapters.external.firecrawl_parser import FirecrawlClient
from app.adapters.openrouter.openrouter_client import OpenRouterClient
from app.adapters.telegram.message_persistence import MessagePersistence
from app.config import AppConfig
from app.core.lang import choose_language
from app.db.database import Database

if TYPE_CHECKING:
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


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
    ) -> None:
        """Handle complete URL processing flow from extraction to summarization."""
        try:
            # Extract and process content
            (
                req_id,
                content_text,
                content_source,
                detected,
            ) = await self.content_extractor.extract_and_process_content(
                message, url_text, correlation_id, interaction_id
            )

            # Choose language and load system prompt
            chosen_lang = choose_language(self.cfg.runtime.preferred_lang, detected)
            system_prompt = await self._load_system_prompt(chosen_lang)

            logger.debug(
                "language_choice",
                extra={"detected": detected, "chosen": chosen_lang, "cid": correlation_id},
            )

            # Notify: language detected with content preview
            content_preview = (
                content_text[:150] + "..." if len(content_text) > 150 else content_text
            )
            await self.response_formatter.send_language_detection_notification(
                message, detected, content_preview
            )

            # Check if content should be chunked
            should_chunk, max_chars, chunks = self.content_chunker.should_chunk_content(
                content_text, chosen_lang
            )

            # Inform the user how the content will be handled
            await self.response_formatter.send_content_analysis_notification(
                message,
                len(content_text),
                max_chars,
                should_chunk,
                chunks,
                self.cfg.openrouter.structured_output_mode,
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

                    # Persist and respond
                    await self._persist_and_respond_chunked(
                        message,
                        req_id,
                        chosen_lang,
                        shaped,
                        llm,
                        len(chunks),
                        correlation_id,
                        interaction_id,
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
            )

            if shaped:
                # Send enhanced summary response (LLM result is handled in summarizer)
                await self.response_formatter.send_enhanced_summary_response(message, shaped, None)
                logger.info("reply_json_sent", extra={"cid": correlation_id, "request_id": req_id})

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
    ) -> None:
        """Persist chunked results and send response."""
        try:
            new_version = self.db.upsert_summary(
                request_id=req_id, lang=chosen_lang, json_payload=json.dumps(shaped)
            )
            self.db.update_request_status(req_id, "ok")
            self._audit("INFO", "summary_upserted", {"request_id": req_id, "version": new_version})
        except Exception as e:  # noqa: BLE001
            logger.error("persist_summary_error", extra={"error": str(e), "cid": correlation_id})

        if interaction_id:
            self._update_user_interaction(
                interaction_id=interaction_id,
                response_sent=True,
                response_type="summary",
                request_id=req_id,
            )

        # Send enhanced results
        await self.response_formatter.send_enhanced_summary_response(
            message, shaped, llm, chunks=chunk_count
        )
        logger.info("reply_json_sent", extra={"cid": correlation_id, "request_id": req_id})

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

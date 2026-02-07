"""Content chunking and aggregation for large texts."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from app.core.async_utils import raise_if_cancelled
from app.core.html_utils import chunk_sentences, split_sentences
from app.core.lang import LANG_RU
from app.core.summary_aggregate import aggregate_chunk_summaries
from app.core.summary_contract import validate_and_shape_summary

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.adapters.external.response_formatter import ResponseFormatter
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.config import AppConfig

logger = logging.getLogger(__name__)


class ContentChunker:
    """Handles content chunking and chunk aggregation for large texts."""

    def __init__(
        self,
        cfg: AppConfig,
        openrouter: LLMClientProtocol,
        response_formatter: ResponseFormatter,
        audit_func: Callable[[str, str, dict], None],
        sem: Callable[[], Any],
    ) -> None:
        self.cfg = cfg
        self.openrouter = openrouter
        self.response_formatter = response_formatter
        self._audit = audit_func
        self._sem = sem

    def estimate_max_chars_for_model(self, model_name: str | None, base_default: int) -> int:
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
            # - Gemini 2.5 Pro: 1,000,000 tokens
            if "gemini-2.5" in name or "2.5-pro" in name or "gemini-2-5" in name:
                return max(base_default, tok(1_000_000))  # ≈ 3,000,000 chars

            # Other generous defaults for known large-context families
            # No other families used in this deployment

            return int(base_default)
        except Exception as exc:
            raise_if_cancelled(exc)
            return int(base_default)

    def should_chunk_content(
        self, content_text: str, chosen_lang: str
    ) -> tuple[bool, int, list[str] | None]:
        """Determine if content should be chunked and return chunking parameters."""
        # Be defensive against MagicMock configs in tests: only honor proper types
        _enable_chunking_val = getattr(self.cfg.runtime, "enable_chunking", False)
        enable_chunking = _enable_chunking_val if isinstance(_enable_chunking_val, bool) else False
        _max_chars_val = getattr(self.cfg.runtime, "chunk_max_chars", 200000)
        configured_max = _max_chars_val if isinstance(_max_chars_val, int) else 200000

        # Choose model to estimate context threshold: prefer long_context_model if configured and string
        _lc_model = getattr(self.cfg.openrouter, "long_context_model", None)
        _primary_model = getattr(self.cfg.openrouter, "model", "")
        threshold_model = (
            _lc_model
            if isinstance(_lc_model, str) and _lc_model
            else (_primary_model if isinstance(_primary_model, str) else "")
        )
        # Nudge toward chunking earlier to reduce long latencies
        tuned_base = int(configured_max * 0.8)
        max_chars = self.estimate_max_chars_for_model(threshold_model, tuned_base)
        content_len = len(content_text)
        chunks: list[str] | None = None

        if enable_chunking and content_len > max_chars:
            logger.info(
                "chunking_enabled",
                extra={
                    "configured_max": configured_max,
                    "adaptive_max": max_chars,
                    "model_for_threshold": threshold_model,
                },
            )
            try:
                sentences = split_sentences(content_text, "ru" if chosen_lang == LANG_RU else "en")
                chunk_size = max(4000, min(12000, max_chars // 10))
                chunk_size = min(chunk_size, max_chars)
                chunks = chunk_sentences(sentences, max_chars=chunk_size)
                logger.info(
                    "chunking_chunk_size",
                    extra={"chunk_size": chunk_size, "chunks": len(chunks)},
                )
            except Exception as exc:
                raise_if_cancelled(exc)
                chunks = None

        return enable_chunking and content_len > max_chars and chunks is not None, max_chars, chunks

    async def process_chunks(
        self,
        chunks: list[str],
        system_prompt: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Process chunks and aggregate summaries."""
        chunk_summaries: list[dict[str, Any]] = []

        async def _process_chunk(idx: int, chunk: str) -> dict[str, Any] | None:
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
                # Use structured output format
                response_format_cf = self._build_structured_response_format()
                # Use dynamic token budget based on chunk size
                chunk_tokens = max(1024, min(4096, len(chunk) // 4 + 1024))
                resp = await self.openrouter.chat(
                    messages,
                    temperature=self.cfg.openrouter.temperature,
                    max_tokens=chunk_tokens,
                    top_p=self.cfg.openrouter.top_p,
                    request_id=req_id,
                    response_format=response_format_cf,
                )
            if resp.status != "ok":
                logger.warning(
                    "chunk_summary_llm_error",
                    extra={
                        "cid": correlation_id,
                        "status": resp.status,
                        "error": resp.error_text,
                        "chunk_index": idx,
                    },
                )
                return None

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
            except Exception as exc:
                raise_if_cancelled(exc)
                parsed = None
            try:
                if parsed is None and (resp.response_text or "").strip():
                    parsed = json.loads((resp.response_text or "").strip().strip("` "))
            except Exception as exc:
                raise_if_cancelled(exc)
                parsed = None
            if parsed is not None:
                try:
                    return validate_and_shape_summary(parsed)
                except Exception as exc:
                    raise_if_cancelled(exc)
            return None

        _chunk_concurrency = getattr(self.cfg.runtime, "max_concurrent_calls", 4)
        _chunk_sem = asyncio.Semaphore(_chunk_concurrency)

        async def _bounded_process(idx: int, chunk: str) -> dict[str, Any] | None:
            async with _chunk_sem:
                return await _process_chunk(idx, chunk)

        tasks = [
            asyncio.create_task(_bounded_process(idx, chunk))
            for idx, chunk in enumerate(chunks, start=1)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise_if_cancelled(result)
                logger.error(
                    "chunk_summary_processing_failed",
                    extra={"cid": correlation_id, "error": str(result)},
                )
                continue
            if isinstance(result, dict):
                chunk_summaries.append(result)

        # Aggregate chunk summaries into final draft
        if chunk_summaries:
            aggregated = aggregate_chunk_summaries(chunk_summaries)

            # Recursive Summarization: Synthesize the final summary from the aggregated chunks
            # This ensures the final output is cohesive and not just a concatenation of parts
            synthesized = await self._synthesize_chunks(
                aggregated, system_prompt, chosen_lang, req_id, correlation_id
            )
            if synthesized:
                return validate_and_shape_summary(synthesized)

            # Fallback to aggregated if synthesis fails
            return validate_and_shape_summary(aggregated)
        return None

    async def _synthesize_chunks(
        self,
        aggregated: dict[str, Any],
        system_prompt: str,
        chosen_lang: str,
        req_id: int,
        correlation_id: str | None,
    ) -> dict[str, Any] | None:
        """Synthesize a final cohesive summary from aggregated chunk summaries."""
        # Convert aggregated dict to a text representation for the LLM
        # We focus on the key components: tldr, summary_250, key_ideas
        context_text = (
            f"TLDR DRAFT:\n{aggregated.get('tldr', '')}\n\n"
            f"DETAILED SUMMARY DRAFT:\n{aggregated.get('summary_250', '')}\n\n"
            f"KEY IDEAS DRAFT:\n{json.dumps(aggregated.get('key_ideas', []), ensure_ascii=False)}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Synthesize the following draft summaries (generated from article chunks) into a single, cohesive, high-quality summary. "
                    f"Ensure the flow is natural and redundant information is removed. "
                    f"Output ONLY a valid JSON object matching the schema.\n"
                    f"Respond in {'Russian' if chosen_lang == LANG_RU else 'English'}.\n\n"
                    f"DRAFT CONTENT START\n{context_text}\nDRAFT CONTENT END"
                ),
            },
        ]

        async with self._sem():
            # Use structured output format
            response_format_cf = self._build_structured_response_format()
            resp = await self.openrouter.chat(
                messages,
                temperature=self.cfg.openrouter.temperature,
                max_tokens=self.cfg.openrouter.max_tokens or 4096,
                top_p=self.cfg.openrouter.top_p,
                request_id=req_id,
                response_format=response_format_cf,
            )

        if resp.status != "ok":
            logger.warning(
                "synthesis_llm_error",
                extra={
                    "cid": correlation_id,
                    "status": resp.status,
                    "error": resp.error_text,
                },
            )
            return None

        # Parse response (reuse existing parsing logic pattern)
        parsed: dict[str, Any] | None = None
        try:
            if resp.response_json and isinstance(resp.response_json, dict):
                ch = resp.response_json.get("choices") or []
                if ch and isinstance(ch[0], dict):
                    msg0 = ch[0].get("message") or {}
                    p = msg0.get("parsed")
                    if p is not None:
                        parsed = p if isinstance(p, dict) else None
        except Exception as exc:
            raise_if_cancelled(exc)
            parsed = None

        if parsed is None:
            try:
                if (resp.response_text or "").strip():
                    parsed = json.loads((resp.response_text or "").strip().strip("` "))
            except Exception:
                pass

        return parsed

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
            return {"type": "json_object"}
        except Exception as exc:
            raise_if_cancelled(exc)
            # Fallback to basic JSON object mode
            return {"type": "json_object"}

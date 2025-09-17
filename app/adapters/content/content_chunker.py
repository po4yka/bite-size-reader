"""Content chunking and aggregation for large texts."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from collections.abc import Callable

from app.config import AppConfig
from app.core.html_utils import chunk_sentences, split_sentences
from app.core.lang import LANG_RU
from app.core.summary_aggregate import aggregate_chunk_summaries
from app.core.summary_contract import validate_and_shape_summary

if TYPE_CHECKING:
    from app.adapters.openrouter.openrouter_client import OpenRouterClient
    from app.adapters.external.response_formatter import ResponseFormatter

logger = logging.getLogger(__name__)


class ContentChunker:
    """Handles content chunking and chunk aggregation for large texts."""

    def __init__(
        self,
        cfg: AppConfig,
        openrouter: OpenRouterClient,
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
        max_chars = self.estimate_max_chars_for_model(threshold_model, configured_max)
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
                chunks = chunk_sentences(sentences, max_chars=2000)
            except Exception:
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
                        parsed = json.loads((resp.response_text or "").strip().strip("` "))
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
            return validate_and_shape_summary(aggregated)
        return None

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

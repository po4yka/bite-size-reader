"""Quality filtering logic for extracted content."""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.adapters.external.firecrawl.models import FirecrawlResult
    from app.adapters.llm.protocol import LLMClientProtocol
    from app.adapter_models.llm.llm_models import LLMCallResult

from app.core.html_utils import clean_markdown_article_text, html_to_text
from app.core.logging_utils import get_logger

logger = get_logger(__name__)

LowValueReason = Literal[
    "empty_after_cleaning",
    "overlay_content_detected",
    "content_too_short",
    "content_low_variation",
    "content_high_repetition",
    "nav_stub_detected",
]


def detect_low_value_content(crawl: FirecrawlResult) -> dict[str, Any] | None:
    """Detect low-value Firecrawl responses that should halt processing."""

    text_candidates: list[str] = []
    if crawl.content_markdown and crawl.content_markdown.strip():
        text_candidates.append(clean_markdown_article_text(crawl.content_markdown))
    if crawl.content_html and crawl.content_html.strip():
        text_candidates.append(html_to_text(crawl.content_html))

    primary_text = next((t for t in text_candidates if t and t.strip()), "")
    normalized = re.sub(r"\s+", " ", primary_text).strip()

    words_raw = re.findall(r"[\w']+", normalized)
    words = [w.lower() for w in words_raw if w]
    word_count = len(words)
    unique_word_count = len(set(words))

    top_word: str | None = None
    top_ratio = 0.0
    if words:
        counter = Counter(words)
        top_word, top_count = counter.most_common(1)[0]
        top_ratio = top_count / word_count if word_count else 0.0

    overlay_terms = {
        "accept",
        "close",
        "cookie",
        "cookies",
        "consent",
        "login",
        "signin",
        "signup",
        "subscribe",
    }
    overlay_ratio = sum(1 for w in words if w in overlay_terms) / word_count if word_count else 0.0

    # Count "substantive sentences" -- sequences of 10+ words ending
    # with sentence-terminal punctuation (.!?) in the normalized text.
    substantive_sentence_count = len(
        [s for s in re.split(r"[.!?]+", normalized) if len(re.findall(r"[\w']+", s)) >= 10]
    )

    reason: LowValueReason | None = None
    if not normalized or word_count == 0:
        reason = "empty_after_cleaning"
    elif overlay_ratio >= 0.7 and len(normalized) < 600:
        reason = "overlay_content_detected"
    elif len(normalized) < 48 and word_count <= 2:
        reason = "content_too_short"
    elif len(normalized) < 120 and (
        unique_word_count <= 3 or (word_count >= 4 and top_ratio >= 0.8)
    ):
        reason = "content_low_variation"
    elif word_count >= 6 and top_ratio >= 0.92:
        reason = "content_high_repetition"
    elif word_count < 100 and substantive_sentence_count < 2:
        reason = "nav_stub_detected"

    if reason:
        return {
            "reason": reason,
            "preview": normalized[:200],
            "metrics": {
                "char_length": len(normalized),
                "word_count": word_count,
                "unique_word_count": unique_word_count,
                "top_word": top_word,
                "top_ratio": top_ratio,
                "overlay_ratio": overlay_ratio,
                "substantive_sentence_count": substantive_sentence_count,
            },
        }
    return None


def is_gray_zone_for_llm_check(reason: LowValueReason, metrics: dict[str, Any]) -> bool:
    """Determine if the heuristic verdict is ambiguous enough to warrant LLM review."""
    if reason != "nav_stub_detected":
        return False
    wc = metrics.get("word_count", 0)
    ssc = metrics.get("substantive_sentence_count", 0)
    return 15 <= wc <= 150 and ssc <= 3


_QUALITY_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "quality_check_system.txt"
_quality_system_prompt: str | None = None


def _load_quality_system_prompt() -> str:
    global _quality_system_prompt
    if _quality_system_prompt is None:
        _quality_system_prompt = _QUALITY_PROMPT_PATH.read_text(encoding="utf-8").strip()
    return _quality_system_prompt


async def classify_content_quality_llm(
    text_preview: str,
    metrics: dict[str, Any],
    llm_client: LLMClientProtocol,
    *,
    flash_model: str,
    flash_fallback_models: tuple[str, ...] | list[str],
    timeout_sec: float = 3.0,
    confidence_threshold: float = 0.7,
    request_id: int | None = None,
) -> tuple[bool, LLMCallResult | None]:
    """Ask LLM whether extracted text is real content or a stub.

    Returns (is_stub, llm_result). On any failure, defers to the heuristic
    verdict by returning (True, llm_result_or_None).
    """
    system_prompt = _load_quality_system_prompt()
    user_message = (
        f"Text (first 500 chars): {text_preview[:500]}\n"
        f"Word count: {metrics.get('word_count', 0)}\n"
        f"Substantive sentences: {metrics.get('substantive_sentence_count', 0)}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    llm_result: LLMCallResult | None = None
    try:
        llm_result = await asyncio.wait_for(
            llm_client.chat(
                messages,
                temperature=0.0,
                max_tokens=50,
                model_override=flash_model,
                fallback_models_override=flash_fallback_models,
                request_id=request_id,
                response_format={"type": "json_object"},
            ),
            timeout=timeout_sec,
        )
    except TimeoutError:
        logger.warning("quality_llm_timeout", extra={"request_id": request_id})
        return True, None
    except Exception:
        logger.warning("quality_llm_error", extra={"request_id": request_id}, exc_info=True)
        return True, llm_result

    try:
        import json_repair

        raw = json_repair.loads(llm_result.response_text or "{}")
        parsed: dict[str, Any] = raw if isinstance(raw, dict) else {}
        classification = parsed.get("classification", "stub")
        confidence = float(parsed.get("confidence", 0.0))
    except Exception:
        logger.warning(
            "quality_llm_parse_error",
            extra={"request_id": request_id, "response": llm_result.response_text},
        )
        return True, llm_result

    if classification == "real_content" and confidence >= confidence_threshold:
        return False, llm_result
    return True, llm_result

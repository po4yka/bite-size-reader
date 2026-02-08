"""Quality filtering logic for extracted content."""

from __future__ import annotations

import re
from collections import Counter
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from app.adapters.external.firecrawl_parser import FirecrawlResult

from app.core.html_utils import clean_markdown_article_text, html_to_text

LowValueReason = Literal[
    "empty_after_cleaning",
    "overlay_content_detected",
    "content_too_short",
    "content_low_variation",
    "content_high_repetition",
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

    words_raw = re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ']+", normalized)
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
            },
        }
    return None

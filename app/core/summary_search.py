"""Search/RAG optimization for summaries.

Builds query expansion keywords, semantic boosters, and normalizes
semantic chunks for retrieval-augmented generation.
Extracted from summary_contract.py.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.nlp import extract_keywords_tfidf
from app.core.text_utils import cap_text, clean_string_list, dedupe_case_insensitive

# Legacy alias kept for type annotations
SummaryJSON = dict[str, Any]


def shape_query_expansion_keywords(payload: SummaryJSON, base_text: str) -> list[str]:
    """Build a diversified list of query expansion keywords."""
    seeds = clean_string_list(payload.get("query_expansion_keywords"))

    # Harvest from topic tags, seo keywords, key ideas
    topics = [
        str(t).strip().lstrip("#") for t in payload.get("topic_tags", []) or [] if str(t).strip()
    ]
    seo = [str(s).strip() for s in payload.get("seo_keywords", []) or [] if str(s).strip()]
    ideas = [str(i).strip() for i in payload.get("key_ideas", []) or [] if str(i).strip()]
    seeds.extend(topics)
    seeds.extend(seo)
    seeds.extend(ideas)

    # Add TF-IDF keywords from text
    tfidf = extract_keywords_tfidf(base_text, topn=40)
    seeds.extend(tfidf)

    deduped = dedupe_case_insensitive(seeds)
    trimmed = deduped[:30]

    # Ensure we have at least 20 items by repeating from tfidf if needed
    if len(trimmed) < 20:
        for term in tfidf:
            if term not in trimmed:
                trimmed.append(term)
            if len(trimmed) >= 20:
                break

    return trimmed[:30]


def shape_semantic_boosters(payload: SummaryJSON, base_text: str) -> list[str]:
    """Create embedding-friendly standalone booster sentences."""
    boosters = clean_string_list(payload.get("semantic_boosters"))

    # Extract sentences from summary text as fallback
    sentences = re.split(r"(?<=[.!?])\s+", base_text)
    sentences = [s.strip() for s in sentences if s and len(s.strip()) > 20]

    for sentence in sentences:
        if len(boosters) >= 15:
            break
        if sentence not in boosters:
            boosters.append(sentence)

    if not boosters:
        boosters = sentences[:10]

    # Cap length and count
    boosters = [cap_text(sentence, 320) for sentence in boosters if sentence.strip()]
    return boosters[:15]


def shape_semantic_chunks(
    raw_chunks: Any,
    *,
    article_id: str | None,
    topics: list[str],
    language: str | None,
) -> list[dict[str, Any]]:
    """Normalize semantic chunk payloads."""
    if not isinstance(raw_chunks, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_chunks:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("content") or "").strip()
        if not text:
            continue
        local_summary = str(item.get("local_summary") or item.get("summary") or "").strip()
        local_summary = cap_text(local_summary, 480) if local_summary else ""
        local_keywords = clean_string_list(item.get("local_keywords"), limit=8)

        normalized.append(
            {
                "article_id": str(item.get("article_id") or article_id or "").strip() or None,
                "section": item.get("section"),
                "language": str(item.get("language") or language or "").strip() or None,
                "topics": clean_string_list(item.get("topics") or topics),
                "text": text,
                "local_summary": local_summary,
                "local_keywords": local_keywords,
            }
        )

    return normalized

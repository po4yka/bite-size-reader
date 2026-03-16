from __future__ import annotations

import re
from typing import Any

from app.core.summary_contract_impl.common import SummaryJSON, clean_string_list
from app.core.summary_contract_impl.text_shaping import extract_keywords_tfidf
from app.core.summary_text_utils import (
    cap_text as _cap_text,
    dedupe_case_insensitive as _dedupe_case_insensitive,
)


def shape_query_expansion_keywords(payload: SummaryJSON, base_text: str) -> list[str]:
    """Build a diversified list of query expansion keywords."""
    seeds = clean_string_list(payload.get("query_expansion_keywords"))
    topics = [
        str(tag).strip().lstrip("#")
        for tag in payload.get("topic_tags", []) or []
        if str(tag).strip()
    ]
    seo = [str(item).strip() for item in payload.get("seo_keywords", []) or [] if str(item).strip()]
    ideas = [str(item).strip() for item in payload.get("key_ideas", []) or [] if str(item).strip()]
    seeds.extend(topics)
    seeds.extend(seo)
    seeds.extend(ideas)

    tfidf = extract_keywords_tfidf(base_text, topn=40)
    seeds.extend(tfidf)

    deduped = _dedupe_case_insensitive(seeds)
    trimmed = deduped[:30]

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
    sentences = re.split(r"(?<=[.!?])\s+", base_text)
    sentences = [
        sentence.strip() for sentence in sentences if sentence and len(sentence.strip()) > 20
    ]

    boosters = [_cap_text(booster, 320) for booster in boosters if booster.strip()]

    for sentence in sentences:
        if len(boosters) >= 15:
            break
        capped = _cap_text(sentence, 320)
        if capped not in boosters:
            boosters.append(capped)

    if not boosters:
        boosters = [_cap_text(sentence, 320) for sentence in sentences[:10] if sentence.strip()]

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
        local_summary = _cap_text(local_summary, 480) if local_summary else ""
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


def shape_rag_fields(payload: SummaryJSON) -> None:
    metadata = payload.get("metadata") or {}
    base_text = " ".join(
        [
            payload.get("summary_1000") or "",
            payload.get("summary_250") or "",
            payload.get("tldr") or "",
        ]
    ).strip()
    topics_clean = [tag.lstrip("#") for tag in payload.get("topic_tags") or []]
    language = payload.get("language") or metadata.get("language")
    article_id = payload.get("article_id") or metadata.get("canonical_url") or metadata.get("url")
    if article_id:
        payload["article_id"] = str(article_id).strip()
    else:
        payload.setdefault("article_id", None)

    payload["query_expansion_keywords"] = shape_query_expansion_keywords(payload, base_text)
    payload["semantic_boosters"] = shape_semantic_boosters(payload, base_text)
    raw_chunks = payload.get("semantic_chunks") or payload.get("chunks") or []
    payload["semantic_chunks"] = shape_semantic_chunks(
        raw_chunks,
        article_id=payload.get("article_id"),
        topics=topics_clean,
        language=language,
    )

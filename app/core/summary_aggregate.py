from __future__ import annotations

import contextlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def _dedupe_list(items: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        s = str(it).strip()
        if not s:
            continue
        key = s.lower()
        if key not in seen:
            seen.add(key)
            out.append(s)
            if limit is not None and len(out) >= limit:
                break
    return out


def _extract_sentences(text: str) -> list[str]:
    """Split text into sentences, filtering short fragments."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in parts if len(s.strip()) > 15]


def _dedupe_sentences(parts: list[str]) -> str:
    """Join text parts with sentence-level deduplication."""
    seen: set[str] = set()
    result_sentences: list[str] = []
    for part in parts:
        for sentence in _extract_sentences(part):
            key = sentence.lower().strip()
            if key not in seen:
                seen.add(key)
                result_sentences.append(sentence)
    return " ".join(result_sentences)


def _select_best_summary_250(parts: list[str]) -> str:
    """Select the single most informative chunk summary for summary_250.

    Picks the longest non-duplicate entry (most informative single sentence).
    """
    deduped = _dedupe_list(parts)
    if not deduped:
        return ""
    # Select the longest (most informative) entry
    return max(deduped, key=len)


def _merge_entities(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    def _lst(x: Any) -> list[str]:
        return [str(i) for i in (x or [])]

    return {
        "people": _dedupe_list(_lst(a.get("people")) + _lst(b.get("people"))),
        "organizations": _dedupe_list(_lst(a.get("organizations")) + _lst(b.get("organizations"))),
        "locations": _dedupe_list(_lst(a.get("locations")) + _lst(b.get("locations"))),
    }


def _merge_key_stats(
    a: list[dict[str, Any]], b: list[dict[str, Any]], limit: int = 20
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in (a or []) + (b or []):
        try:
            label = str(item.get("label", "")).strip()
            if not label:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "label": label,
                    "value": float(item.get("value", 0)),
                    "unit": item.get("unit"),
                    "source_excerpt": item.get("source_excerpt"),
                }
            )
            if len(out) >= limit:
                break
        except Exception:
            logger.debug("aggregate_item_skipped", exc_info=True)
            continue
    return out


def aggregate_chunk_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate multiple chunk-level summaries into a single summary JSON.

    - Concatenates single-sentence chunk summaries to form final summaries, respecting caps later.
    - Unions arrays and entities with deduplication and sensible limits.
    - Sums estimated_reading_time_min if provided, otherwise 0.
    - Leaves readability to be computed/validated downstream.
    """
    if not summaries:
        return {
            "summary_250": "",
            "summary_1000": "",
            "tldr": "",
            "key_ideas": [],
            "topic_tags": [],
            "entities": {"people": [], "organizations": [], "locations": []},
            "estimated_reading_time_min": 0,
            "key_stats": [],
            "answered_questions": [],
            "readability": {"method": "Flesch-Kincaid", "score": 0.0, "level": "Unknown"},
            "seo_keywords": [],
            "insights": {
                "topic_overview": "",
                "new_facts": [],
                "open_questions": [],
                "suggested_sources": [],
                "expansion_topics": [],
                "next_exploration": [],
                "caution": None,
            },
        }

    s250_parts: list[str] = []
    s1000_parts: list[str] = []
    tldr_parts: list[str] = []
    key_ideas: list[str] = []
    topic_tags: list[str] = []
    entities: dict[str, list[str]] = {"people": [], "organizations": [], "locations": []}
    ert_sum = 0
    key_stats: list[dict[str, Any]] = []
    answered: list[str] = []
    seo_keywords: list[str] = []
    topic_overview_parts: list[str] = []
    caution_parts: list[str] = []
    fact_map: dict[str, dict[str, Any]] = {}
    open_questions: list[str] = []
    suggested_sources: list[str] = []
    expansion_topics: list[str] = []
    next_exploration: list[str] = []

    for s in summaries:
        try:
            s250 = str(s.get("summary_250", "")).strip()
            if s250:
                s250_parts.append(s250)
            s1000_value = str(s.get("summary_1000", "") or s.get("tldr", "")).strip()
            if s1000_value:
                s1000_parts.append(s1000_value)
            tldr_value = str(s.get("tldr", "") or s1000_value).strip()
            if tldr_value:
                tldr_parts.append(tldr_value)
            key_ideas.extend([str(x) for x in (s.get("key_ideas") or [])])
            topic_tags.extend([str(x) for x in (s.get("topic_tags") or [])])
            entities = _merge_entities(entities, s.get("entities") or {})
            with contextlib.suppress(Exception):
                ert_sum += int(s.get("estimated_reading_time_min") or 0)
            key_stats = _merge_key_stats(key_stats, s.get("key_stats") or [])
            answered.extend([str(x) for x in (s.get("answered_questions") or [])])
            seo_keywords.extend([str(x) for x in (s.get("seo_keywords") or [])])
            insights_payload = s.get("insights") or {}
            if isinstance(insights_payload, dict):
                overview = str(insights_payload.get("topic_overview", "")).strip()
                if overview:
                    topic_overview_parts.append(overview)
                caution = str(insights_payload.get("caution", "")).strip()
                if caution:
                    caution_parts.append(caution)
                for fact in insights_payload.get("new_facts", []) or []:
                    if not isinstance(fact, dict):
                        continue
                    fact_text = str(fact.get("fact", "")).strip()
                    if not fact_text:
                        continue
                    key = fact_text.lower()
                    if key in fact_map:
                        continue
                    fact_map[key] = {
                        "fact": fact_text,
                        "why_it_matters": str(fact.get("why_it_matters", "")).strip() or None,
                        "source_hint": str(fact.get("source_hint", "")).strip() or None,
                        "confidence": fact.get("confidence"),
                    }
                open_questions.extend(
                    [str(x).strip() for x in (insights_payload.get("open_questions") or [])]
                )
                suggested_sources.extend(
                    [str(x).strip() for x in (insights_payload.get("suggested_sources") or [])]
                )
                expansion_topics.extend(
                    [str(x).strip() for x in (insights_payload.get("expansion_topics") or [])]
                )
                next_exploration.extend(
                    [str(x).strip() for x in (insights_payload.get("next_exploration") or [])]
                )
        except Exception:
            logger.debug("aggregate_chunk_item_skipped", exc_info=True)
            continue

    # For summary_250: select the single best chunk summary (most informative)
    s250_joined = _select_best_summary_250(s250_parts)
    # For summary_1000/tldr: deduplicate at sentence level for coherence
    s1000_joined = _dedupe_sentences(_dedupe_list(s1000_parts))
    tldr_joined = _dedupe_sentences(_dedupe_list(tldr_parts))
    # Ensure tldr is always longer than summary_1000
    if tldr_joined and s1000_joined and len(tldr_joined) <= len(s1000_joined):
        tldr_joined = s1000_joined + " " + tldr_joined
    insights = {
        "topic_overview": "\n\n".join(_dedupe_list(topic_overview_parts, limit=3)),
        "new_facts": list(fact_map.values())[:8],
        "open_questions": _dedupe_list(open_questions, limit=6),
        "suggested_sources": _dedupe_list(suggested_sources, limit=6),
        "expansion_topics": _dedupe_list(expansion_topics, limit=6),
        "next_exploration": _dedupe_list(next_exploration, limit=6),
        "caution": "\n\n".join(_dedupe_list(caution_parts, limit=2)) or None,
    }

    return {
        "summary_250": s250_joined,
        "summary_1000": s1000_joined or tldr_joined or s250_joined,
        "tldr": tldr_joined or s1000_joined or s250_joined,
        "key_ideas": _dedupe_list(key_ideas, limit=10),
        "topic_tags": _dedupe_list(topic_tags, limit=8),
        "entities": entities,
        "estimated_reading_time_min": max(0, ert_sum),
        "key_stats": key_stats,
        "answered_questions": _dedupe_list(answered),
        "readability": {"method": "Flesch-Kincaid", "score": 0.0, "level": "Unknown"},
        "seo_keywords": _dedupe_list(seo_keywords, limit=15),
        "insights": insights,
    }

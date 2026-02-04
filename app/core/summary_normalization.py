"""Summary-specific normalization and enrichment logic.

Handles field name mapping, entity normalization, TL;DR enrichment,
insight shaping, and summary backfill from supporting fields.
Extracted from summary_contract.py.
"""

from __future__ import annotations

from typing import Any

from app.core.text_utils import (
    cap_text,
    clean_string_list,
    dedupe_case_insensitive,
    is_numeric,
    normalize_whitespace,
    similarity_ratio,
)

# Legacy alias kept for type annotations in summary_contract.py
SummaryJSON = dict[str, Any]


def normalize_field_names(payload: SummaryJSON) -> SummaryJSON:
    """Normalize field names from camelCase to snake_case.

    Handles common field name variations that LLMs might return.
    """
    field_mapping = {
        # Summary fields
        "summary": "summary_1000",  # Map generic "summary" to the 1000-char slot
        "summary250": "summary_250",
        "summary1000": "summary_1000",
        "summary_250": "summary_250",  # Already correct
        "summary_1000": "summary_1000",
        # Key ideas and tags
        "keyideas": "key_ideas",
        "keyIdeas": "key_ideas",
        "key_ideas": "key_ideas",  # Already correct
        "topictags": "topic_tags",
        "topicTags": "topic_tags",
        "topic_tags": "topic_tags",  # Already correct
        # Reading time
        "estimatedreadingtimemin": "estimated_reading_time_min",
        "estimatedReadingTimeMin": "estimated_reading_time_min",
        "estimated_reading_time_min": "estimated_reading_time_min",  # Already correct
        # Key stats
        "keystats": "key_stats",
        "keyStats": "key_stats",
        "key_stats": "key_stats",  # Already correct
        # Answered questions
        "answeredquestions": "answered_questions",
        "answeredQuestions": "answered_questions",
        "answered_questions": "answered_questions",  # Already correct
        # SEO keywords
        "seokeywords": "seo_keywords",
        "seoKeywords": "seo_keywords",
        "seo_keywords": "seo_keywords",  # Already correct
        # New fields
        "extractivequotes": "extractive_quotes",
        "extractiveQuotes": "extractive_quotes",
        "questionsanswered": "questions_answered",
        "questionsAnswered": "questions_answered",
        "topictaxonomy": "topic_taxonomy",
        "topicTaxonomy": "topic_taxonomy",
        "hallucinationrisk": "hallucination_risk",
        "hallucinationRisk": "hallucination_risk",
        "forwardedpostextras": "forwarded_post_extras",
        "forwardedPostExtras": "forwarded_post_extras",
        "keypointstoremember": "key_points_to_remember",
        "keyPointsToRemember": "key_points_to_remember",
    }

    normalized = {}
    for key, value in payload.items():
        # Map field names
        normalized_key = field_mapping.get(key, key)
        normalized[normalized_key] = value

    return normalized


# ---------------------------------------------------------------------------
# Entity normalization
# ---------------------------------------------------------------------------

_ENTITY_KEY_ALIASES = {
    "person": "people",
    "persons": "people",
    "individual": "people",
    "individuals": "people",
    "people": "people",
    "organization": "organizations",
    "organizations": "organizations",
    "org": "organizations",
    "orgs": "organizations",
    "company": "organizations",
    "companies": "organizations",
    "institution": "organizations",
    "institutions": "organizations",
    "location": "locations",
    "locations": "locations",
    "place": "locations",
    "places": "locations",
    "country": "locations",
    "countries": "locations",
    "city": "locations",
    "cities": "locations",
}


def resolve_entity_bucket(name: Any) -> str | None:
    """Map entity type names to canonical bucket names."""
    if name is None:
        return None
    normalized = str(name).strip().lower()
    if not normalized:
        return None
    bucket = _ENTITY_KEY_ALIASES.get(normalized, normalized)
    return bucket if bucket in {"people", "organizations", "locations"} else None


def coerce_entity_values(value: Any) -> list[str]:
    """Extract string values from nested dicts/lists recursively."""
    result: list[str] = []
    if value is None:
        return result
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            result.append(candidate)
        return result
    if isinstance(value, int | float):
        return [str(value)]
    if isinstance(value, dict):
        preferred_keys = ("entities", "items", "names", "values", "list", "members")
        extracted = False
        for key in preferred_keys:
            if key in value:
                result.extend(coerce_entity_values(value[key]))
                extracted = True
        if not extracted:
            fallback_keys = ("name", "label", "entity", "text", "value")
            for key in fallback_keys:
                if key in value:
                    result.extend(coerce_entity_values(value[key]))
                    extracted = True
            if not extracted:
                for item in value.values():
                    result.extend(coerce_entity_values(item))
        return result
    if isinstance(value, list | tuple | set):
        for item in value:
            result.extend(coerce_entity_values(item))
        return result
    return [str(value)]


def normalize_entities_field(raw: Any) -> dict[str, list[str]]:
    """Convert entities to canonical ``{people, organizations, locations}`` structure."""
    buckets: dict[str, list[str]] = {"people": [], "organizations": [], "locations": []}

    if isinstance(raw, dict):
        for key, value in raw.items():
            bucket = resolve_entity_bucket(key)
            if bucket:
                buckets[bucket].extend(coerce_entity_values(value))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                bucket = (
                    resolve_entity_bucket(item.get("type"))
                    or resolve_entity_bucket(item.get("category"))
                    or resolve_entity_bucket(item.get("label"))
                    or resolve_entity_bucket(item.get("group"))
                )
                buckets[bucket or "people"].extend(coerce_entity_values(item))
            else:
                buckets["people"].extend(coerce_entity_values(item))
    else:
        buckets["people"].extend(coerce_entity_values(raw))

    return {
        key: dedupe_case_insensitive(
            [val for val in buckets[key] if isinstance(val, str) and val.strip()]
        )
        for key in buckets
    }


# ---------------------------------------------------------------------------
# TL;DR enrichment
# ---------------------------------------------------------------------------


def tldr_needs_enrichment(tldr: str, summary_1000: str) -> bool:
    """Detect if TLDR is too similar to summary_1000 and needs expansion."""
    tldr_norm = normalize_whitespace(tldr)
    summary_norm = normalize_whitespace(summary_1000)

    if not tldr_norm or not summary_norm:
        return False

    if tldr_norm == summary_norm:
        return True

    sim = similarity_ratio(tldr_norm, summary_norm)
    if sim >= 0.92:
        return True

    if summary_norm.startswith(tldr_norm) or tldr_norm.startswith(summary_norm):
        if abs(len(tldr_norm) - len(summary_norm)) <= 120:
            return True

    return len(tldr_norm) <= len(summary_norm) + 40


def summary_fallback_from_supporting_fields(payload: SummaryJSON) -> str | None:
    """Compose a fallback summary using secondary textual fields."""

    def _add_snippet(snippet: Any) -> None:
        if len(snippets) >= 8:
            return
        text = str(snippet).strip() if snippet is not None else ""
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        snippets.append(text)

    snippets: list[str] = []
    seen: set[str] = set()

    scalar_candidates = (
        payload.get("topic_overview"),
        payload.get("overview"),
    )
    for candidate in scalar_candidates:
        _add_snippet(candidate)

    list_fields = (
        "summary_paragraphs",
        "summary_bullets",
        "highlights",
        "key_points_to_remember",
        "key_ideas",
        "answered_questions",
    )
    for field in list_fields:
        value = payload.get(field)
        if isinstance(value, list | tuple | set):
            for item in value:
                _add_snippet(item)
        elif value is not None:
            _add_snippet(value)

    questions_answered = payload.get("questions_answered")
    if isinstance(questions_answered, list):
        for entry in questions_answered:
            if isinstance(entry, dict):
                question = str(entry.get("question", "")).strip()
                answer = str(entry.get("answer", "")).strip()
                if question and answer:
                    _add_snippet(f"{question}: {answer}")
                elif question:
                    _add_snippet(question)
                elif answer:
                    _add_snippet(answer)
            else:
                _add_snippet(entry)

    extractive_quotes = payload.get("extractive_quotes")
    if isinstance(extractive_quotes, list):
        for quote in extractive_quotes:
            if isinstance(quote, dict):
                _add_snippet(quote.get("text"))
            else:
                _add_snippet(quote)

    insights = payload.get("insights")
    if isinstance(insights, dict):
        _add_snippet(insights.get("topic_overview"))
        _add_snippet(insights.get("caution"))
        new_facts = insights.get("new_facts")
        if isinstance(new_facts, list):
            for fact in new_facts:
                if isinstance(fact, dict):
                    fact_text = str(fact.get("fact", "")).strip()
                    why = str(fact.get("why_it_matters", "")).strip()
                    if fact_text and why:
                        _add_snippet(f"{fact_text} -- {why}")
                    else:
                        _add_snippet(fact_text or why)
                else:
                    _add_snippet(fact)

    if not snippets:
        return None

    combined = " ".join(snippets[:6]).strip()
    return combined or None


def enrich_tldr_from_payload(base_text: str, payload: SummaryJSON) -> str:
    """Expand a TL;DR when it mirrors the 1000-char summary.

    Uses supporting fields (key ideas, highlights, stats, answered questions, insights)
    to add depth so the TL;DR is richer than summary_1000.
    """

    def _add_segment(text: str) -> None:
        cleaned = str(text).strip()
        if not cleaned:
            return
        normalized = normalize_whitespace(cleaned).lower()
        if normalized in seen:
            return
        seen.add(normalized)
        segments.append(cleaned)

    segments: list[str] = []
    seen: set[str] = set()

    _add_segment(base_text)

    key_ideas = clean_string_list(payload.get("key_ideas"), limit=6)
    if key_ideas:
        _add_segment(f"Key ideas: {'; '.join(key_ideas)}.")

    highlights = clean_string_list(payload.get("highlights"), limit=5)
    if highlights:
        _add_segment(f"Highlights: {'; '.join(highlights)}.")

    stats_parts: list[str] = []
    for stat in payload.get("key_stats") or []:
        if not isinstance(stat, dict):
            continue
        label = str(stat.get("label", "")).strip()
        value = stat.get("value")
        if not label or not is_numeric(value):
            continue
        unit_raw = stat.get("unit")
        unit = str(unit_raw).strip() if unit_raw is not None else ""
        unit_part = f" {unit}" if unit else ""
        stats_parts.append(f"{label}: {value}{unit_part}")
    if stats_parts:
        _add_segment(f"Key stats: {'; '.join(stats_parts)}.")

    answered = payload.get("answered_questions")
    if isinstance(answered, list):
        questions: list[str] = []
        for qa in answered:
            if isinstance(qa, dict):
                question = str(qa.get("question", "")).strip()
                answer = str(qa.get("answer", "")).strip()
                if question and answer:
                    questions.append(f"{question} -- {answer}")
                elif question:
                    questions.append(question)
            elif isinstance(qa, str) and qa.strip():
                questions.append(qa.strip())
        if questions:
            deduped = dedupe_case_insensitive(questions)
            _add_segment(f"Questions answered: {'; '.join(deduped)}.")

    insights = payload.get("insights")
    if isinstance(insights, dict):
        topic_overview = str(insights.get("topic_overview", "")).strip()
        if topic_overview:
            _add_segment(topic_overview)
        caution = str(insights.get("caution", "")).strip()
        if caution:
            _add_segment(f"Caution: {caution}")

    fallback = summary_fallback_from_supporting_fields(payload)
    if fallback:
        _add_segment(fallback)

    enriched = " ".join(segments).strip()
    if not enriched:
        return base_text
    return cap_text(enriched, 2000)


# ---------------------------------------------------------------------------
# Insight shaping
# ---------------------------------------------------------------------------


def shape_insights(raw: Any) -> dict[str, Any]:
    """Normalize insights structure."""
    shaped: dict[str, Any] = {
        "topic_overview": "",
        "new_facts": [],
        "open_questions": [],
        "suggested_sources": [],
        "expansion_topics": [],
        "next_exploration": [],
        "caution": None,
    }

    if not isinstance(raw, dict):
        return shaped

    shaped["topic_overview"] = str(raw.get("topic_overview", "")).strip()

    facts: list[dict[str, Any]] = []
    seen_facts: set[str] = set()
    for fact in raw.get("new_facts", []) or []:
        if not isinstance(fact, dict):
            continue
        fact_text = str(fact.get("fact", "")).strip()
        if not fact_text:
            continue
        fact_key = fact_text.lower()
        if fact_key in seen_facts:
            continue
        seen_facts.add(fact_key)
        why_value = str(fact.get("why_it_matters", "")).strip() or None
        source_value = str(fact.get("source_hint", "")).strip() or None
        confidence_raw = fact.get("confidence")
        if isinstance(confidence_raw, int | float):
            confidence_value: float | str | None = float(confidence_raw)
        elif confidence_raw is None:
            confidence_value = None
        else:
            confidence_value = str(confidence_raw).strip() or None
        facts.append(
            {
                "fact": fact_text,
                "why_it_matters": why_value,
                "source_hint": source_value,
                "confidence": confidence_value,
            }
        )
    shaped["new_facts"] = facts

    shaped["open_questions"] = clean_string_list(raw.get("open_questions"))
    shaped["suggested_sources"] = clean_string_list(raw.get("suggested_sources"))
    shaped["expansion_topics"] = clean_string_list(raw.get("expansion_topics"))
    shaped["next_exploration"] = clean_string_list(raw.get("next_exploration"))

    caution_value = str(raw.get("caution", "")).strip()
    shaped["caution"] = caution_value or None

    return shaped

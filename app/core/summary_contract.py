"""Summary contract validation and shaping.

This module is the public API for validating and shaping LLM-produced summaries.
The heavy lifting is delegated to:
- ``app.core.text_utils`` -- pure text utilities
- ``app.core.nlp`` -- NLP functions (readability, TF-IDF)
- ``app.core.summary_normalization`` -- field normalization, entity mapping, enrichment
- ``app.core.summary_search`` -- RAG/search optimization fields
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.nlp import compute_flesch_reading_ease, extract_keywords_tfidf
from app.core.summary_normalization import (
    SummaryJSON,
    enrich_tldr_from_payload,
    normalize_entities_field,
    normalize_field_names,
    shape_insights,
    summary_fallback_from_supporting_fields,
    tldr_needs_enrichment,
)
from app.core.summary_search import (
    shape_query_expansion_keywords,
    shape_semantic_boosters,
    shape_semantic_chunks,
)
from app.core.text_utils import (
    cap_text,
    clean_string_list,
    dedupe_case_insensitive,
    hash_tagify,
    is_numeric,
    normalize_whitespace,
    similarity_ratio,
)
from app.types.summary_types import (
    Entities,
    KeyStat,
    Metadata,
    Readability,
    SemanticChunk,
    SummaryDict,
)

from .summary_schema import SummaryModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backward-compatibility aliases (private names used by external importers)
# ---------------------------------------------------------------------------
_cap_text = cap_text
_normalize_whitespace = normalize_whitespace
_similarity_ratio = similarity_ratio
_is_numeric = is_numeric
_dedupe_case_insensitive = dedupe_case_insensitive
_clean_string_list = clean_string_list
_hash_tagify = hash_tagify
_compute_flesch_reading_ease = compute_flesch_reading_ease
_extract_keywords_tfidf = extract_keywords_tfidf
_normalize_field_names = normalize_field_names
_normalize_entities_field = normalize_entities_field
_tldr_needs_enrichment = tldr_needs_enrichment
_enrich_tldr_from_payload = enrich_tldr_from_payload
_summary_fallback_from_supporting_fields = summary_fallback_from_supporting_fields
_shape_insights = shape_insights
_shape_query_expansion_keywords = shape_query_expansion_keywords
_shape_semantic_boosters = shape_semantic_boosters
_shape_semantic_chunks = shape_semantic_chunks


# Re-export typed versions for stricter typing
__all__ = [
    "Entities",
    "KeyStat",
    "Metadata",
    "Readability",
    "SemanticChunk",
    "SummaryDict",
    "SummaryJSON",
]


def validate_and_shape_summary(payload: SummaryJSON) -> SummaryJSON:
    """Validate and shape a model-produced summary to the canonical contract.

    Pre-processes the payload with complex shaping logic (TF-IDF, readability
    scoring, TL;DR enrichment, entity normalization, etc.) and then passes it
    through the Pydantic ``SummaryModel`` for type coercion, constraint
    enforcement, and default values.
    """
    # Security: Validate input
    if not payload or not isinstance(payload, dict):
        msg = "Summary payload must be a non-empty dictionary"
        raise ValueError(msg)

    # Security: Prevent extremely large payloads
    if len(str(payload)) > 100000:  # 100KB limit
        msg = "Summary payload too large"
        raise ValueError(msg)

    # Normalize field names first
    p: SummaryJSON = normalize_field_names(payload)

    # --- Summary field backfill (before Pydantic, which needs valid values) ---
    tldr = str(p.get("tldr", "")).strip()
    summary_250 = str(p.get("summary_250", "")).strip()
    summary_1000 = str(p.get("summary_1000", "")).strip()

    if not summary_1000 and "summary" in p:
        summary_1000 = str(p.get("summary", "")).strip()

    if not tldr and summary_1000:
        tldr = summary_1000
    if not summary_1000 and tldr:
        summary_1000 = tldr
    if not summary_250 and summary_1000:
        summary_250 = cap_text(summary_1000, 250)
    if not summary_250 and tldr:
        summary_250 = cap_text(tldr, 250)

    if not any((summary_250, summary_1000, tldr)):
        fallback_text = summary_fallback_from_supporting_fields(p)
        if not fallback_text:
            fallback_text = summary_fallback_from_supporting_fields(payload)
        if fallback_text:
            summary_1000 = cap_text(fallback_text, 1000)
            summary_250 = cap_text(summary_1000, 250)
            tldr = summary_1000

    summary_250 = cap_text(summary_250, 250)
    summary_1000 = cap_text(summary_1000, 1000)

    if not summary_1000 and summary_250:
        summary_1000 = summary_250
    if not tldr:
        tldr = summary_1000 or summary_250

    if tldr_needs_enrichment(tldr, summary_1000):
        tldr = enrich_tldr_from_payload(summary_1000 or tldr, p)

    p["summary_250"] = summary_250
    p["summary_1000"] = summary_1000
    p["tldr"] = tldr

    # --- Shape complex fields that Pydantic cannot handle alone ---
    p["key_ideas"] = [str(x).strip() for x in p.get("key_ideas", []) if str(x).strip()]
    p["topic_tags"] = hash_tagify([str(x) for x in p.get("topic_tags", [])])
    p["entities"] = normalize_entities_field(p.get("entities"))

    # readability: compute locally
    rb = p.get("readability") or {}
    method = str(rb.get("method") or "Flesch-Kincaid")
    score_val = rb.get("score")
    level = rb.get("level")
    read_src = p.get("tldr") or p.get("summary_1000") or p.get("summary_250") or ""
    if score_val is None or not is_numeric(score_val) or float(score_val or 0.0) == 0.0:
        score = 0.0
        try:
            score = compute_flesch_reading_ease(read_src)
            method = "Flesch-Kincaid"
        except Exception:
            try:
                score = float(score_val or 0.0)
            except Exception:
                score = 0.0
    else:
        try:
            score = float(score_val or 0.0)
        except Exception:
            score = 0.0

    if not level:
        if score >= 90:
            level = "Very Easy"
        elif score >= 80:
            level = "Easy"
        elif score >= 70:
            level = "Fairly Easy"
        elif score >= 60:
            level = "Standard"
        elif score >= 50:
            level = "Fairly Difficult"
        elif score >= 30:
            level = "Difficult"
        else:
            level = "Very Confusing"
    p["readability"] = {
        "method": method,
        "score": score,
        "level": level,
    }

    # keyterms: populate seo_keywords/topic_tags if missing (best-effort)
    if not p.get("seo_keywords") or not p.get("topic_tags"):
        try:  # pragma: no cover - optional heavy deps
            terms = extract_keywords_tfidf(read_src, topn=10)
            if not p.get("seo_keywords"):
                p["seo_keywords"] = terms[:10]
            if not p.get("topic_tags") and terms:
                p["topic_tags"] = hash_tagify(terms)
        except Exception as e:
            logger.debug("keyword_extraction_failed", extra={"error": str(e)})

    p["insights"] = shape_insights(p.get("insights"))

    # Clean extractive_quotes before Pydantic
    p["extractive_quotes"] = [
        {
            "text": str(q.get("text", "")).strip(),
            "source_span": str(q.get("source_span", "")).strip() or None,
        }
        for q in (p.get("extractive_quotes") or [])
        if isinstance(q, dict) and str(q.get("text", "")).strip()
    ]
    p["highlights"] = [str(h).strip() for h in (p.get("highlights") or []) if str(h).strip()]

    # Clean questions_answered as question-answer pairs
    clean_qa = []
    for qa in p.get("questions_answered") or []:
        if isinstance(qa, dict):
            question = str(qa.get("question", "")).strip()
            answer = str(qa.get("answer", "")).strip()
            if question and answer:
                clean_qa.append({"question": question, "answer": answer})
        elif isinstance(qa, str):
            qa_str = str(qa).strip()
            if qa_str:
                qa_patterns = [
                    r"Q:\s*(.+?)\s*A:\s*(.+)",
                    r"Question:\s*(.+?)\s*Answer:\s*(.+)",
                    r"(.+?)\?\s*(.+)",
                ]
                matched = False
                for pattern in qa_patterns:
                    match = re.search(pattern, qa_str, re.IGNORECASE | re.DOTALL)
                    if match:
                        question = match.group(1).strip()
                        answer = match.group(2).strip()
                        if question and answer:
                            clean_qa.append({"question": question, "answer": answer})
                            matched = True
                            break
                if not matched:
                    clean_qa.append({"question": qa_str, "answer": ""})
    p["questions_answered"] = clean_qa

    p["categories"] = [str(c).strip() for c in (p.get("categories") or []) if str(c).strip()]
    p["key_points_to_remember"] = [
        str(kp).strip() for kp in (p.get("key_points_to_remember") or []) if str(kp).strip()
    ]

    # Clean topic_taxonomy
    clean_taxonomy = []
    for tax in p.get("topic_taxonomy") or []:
        if isinstance(tax, dict) and str(tax.get("label", "")).strip():
            clean_taxonomy.append(
                {
                    "label": str(tax["label"]).strip(),
                    "score": float(tax.get("score", 0.0)) if is_numeric(tax.get("score")) else 0.0,
                    "path": str(tax.get("path", "")).strip() or None,
                }
            )
    p["topic_taxonomy"] = clean_taxonomy

    # RAG-optimized fields
    metadata = p.get("metadata") or {}
    base_text = " ".join(
        [
            p.get("summary_1000") or "",
            p.get("summary_250") or "",
            p.get("tldr") or "",
        ]
    ).strip()
    topics_clean = [t.lstrip("#") for t in p.get("topic_tags") or []]
    language = p.get("language") or metadata.get("language")
    article_id = p.get("article_id") or metadata.get("canonical_url") or metadata.get("url")
    if article_id:
        p["article_id"] = str(article_id).strip()
    else:
        p.setdefault("article_id", None)

    p["query_expansion_keywords"] = shape_query_expansion_keywords(p, base_text)
    p["semantic_boosters"] = shape_semantic_boosters(p, base_text)

    raw_chunks = p.get("semantic_chunks") or p.get("chunks") or []
    p["semantic_chunks"] = shape_semantic_chunks(
        raw_chunks,
        article_id=p.get("article_id"),
        topics=topics_clean,
        language=language,
    )

    # --- Pass through Pydantic for type coercion and constraint enforcement ---
    try:
        model = SummaryModel(**p)
        return model.model_dump()
    except Exception as e:
        logger.debug("pydantic_validation_fallback", extra={"error": str(e)})
        return p


def get_summary_json_schema() -> dict[str, Any]:
    """Return a JSON Schema for the summary contract.

    Uses the Pydantic ``SummaryModel`` to generate the schema.
    """

    def _enforce_no_additional_props(schema_obj: Any) -> Any:
        """Recursively enforce additionalProperties: false on all object schemas."""
        if isinstance(schema_obj, dict):
            if schema_obj.get("type") == "object":
                schema_obj.setdefault("additionalProperties", False)

            for key in ("properties", "$defs", "definitions"):
                if key in schema_obj and isinstance(schema_obj[key], dict):
                    for _, sub in list(schema_obj[key].items()):
                        _enforce_no_additional_props(sub)
            for key in ("items",):
                if key in schema_obj:
                    _enforce_no_additional_props(schema_obj[key])
            for key in ("oneOf", "anyOf", "allOf"):
                if key in schema_obj and isinstance(schema_obj[key], list):
                    for sub in schema_obj[key]:
                        _enforce_no_additional_props(sub)
        elif isinstance(schema_obj, list):
            for sub in schema_obj:
                _enforce_no_additional_props(sub)
        return schema_obj

    def _enforce_required_all(schema_obj: Any) -> Any:
        """Recursively ensure every object declares required for all of its properties."""
        if isinstance(schema_obj, dict):
            if schema_obj.get("type") == "object" and isinstance(
                schema_obj.get("properties"), dict
            ):
                prop_keys = list(schema_obj["properties"].keys())
                schema_obj["required"] = prop_keys

                for _, sub in list(schema_obj["properties"].items()):
                    _enforce_required_all(sub)

            for key in ("items",):
                if key in schema_obj:
                    _enforce_required_all(schema_obj[key])
            for key in ("oneOf", "anyOf", "allOf"):
                if key in schema_obj and isinstance(schema_obj[key], list):
                    for sub in schema_obj[key]:
                        _enforce_required_all(sub)
            for key in ("$defs", "definitions"):
                if key in schema_obj and isinstance(schema_obj[key], dict):
                    for _, sub in list(schema_obj[key].items()):
                        _enforce_required_all(sub)
        elif isinstance(schema_obj, list):
            for sub in schema_obj:
                _enforce_required_all(sub)
        return schema_obj

    schema = SummaryModel.model_json_schema()

    if isinstance(schema, dict):
        schema.setdefault("$schema", "http://json-schema.org/draft-07/schema#")
        schema.setdefault("type", "object")
        _enforce_no_additional_props(schema)
        _enforce_required_all(schema)
        return schema

    return schema

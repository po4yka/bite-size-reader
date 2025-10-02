from __future__ import annotations

from typing import Any

from .summary_schema import PydanticAvailable

# ruff: noqa: E501


SummaryModelT: Any
if PydanticAvailable:
    from .summary_schema import SummaryModel as SummaryModelT


SummaryJSON = dict[str, Any]


def _is_numeric(value: Any) -> bool:
    """Check if a value can be converted to a float."""
    if value is None:
        return False
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def _cap_text(text: str, limit: int) -> str:
    # Security: Validate inputs
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError("Limit must be a positive integer")

    # Security: Prevent extremely large limits
    if limit > 10000:
        raise ValueError("Limit too large")

    if len(text) <= limit:
        return text
    # cut to limit and then trim to last sentence/phrase boundary
    snippet = text[:limit]
    for sep in (". ", "! ", "? ", "; ", ", "):
        idx = snippet.rfind(sep)
        if idx > 0:
            return snippet[: idx + len(sep)].strip()
    return snippet.strip()


def _hash_tagify(tags: list[str], max_tags: int = 10) -> list[str]:
    # Security: Validate inputs
    if not isinstance(tags, list):
        return []
    if not isinstance(max_tags, int) or max_tags <= 0 or max_tags > 100:
        max_tags = 10

    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if not t:
            continue
        # Security: Prevent extremely long tags
        if len(t) > 100:
            continue
        # Security: Prevent dangerous content in tags
        if any(char in t.lower() for char in ["<", ">", "script", "javascript"]):
            continue

        if not t.startswith("#"):
            t = f"#{t}"
        key = t.lower()
        if key not in seen:
            seen.add(key)
            result.append(t)
        if len(result) >= max_tags:
            break
    return result


def _dedupe_case_insensitive(items: list[str]) -> list[str]:
    # Security: Validate inputs
    if not isinstance(items, list):
        return []

    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if not isinstance(it, str):
            continue
        key = it.strip().lower()
        if key and key not in seen:
            # Security: Prevent extremely long items
            if len(key) > 500:
                continue
            # Security: Prevent dangerous content
            if any(char in key for char in ["<", ">", "script", "javascript"]):
                continue
            seen.add(key)
            out.append(it.strip())
    return out


def _summary_fallback_from_supporting_fields(payload: SummaryJSON) -> str | None:
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
                        _add_snippet(f"{fact_text} — {why}")
                    else:
                        _add_snippet(fact_text or why)
                else:
                    _add_snippet(fact)

    if not snippets:
        return None

    combined = " ".join(snippets[:6]).strip()
    return combined or None


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


def _resolve_entity_bucket(name: Any) -> str | None:
    if name is None:
        return None
    normalized = str(name).strip().lower()
    if not normalized:
        return None
    bucket = _ENTITY_KEY_ALIASES.get(normalized, normalized)
    return bucket if bucket in {"people", "organizations", "locations"} else None


def _coerce_entity_values(value: Any) -> list[str]:
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
                result.extend(_coerce_entity_values(value[key]))
                extracted = True
        if not extracted:
            fallback_keys = ("name", "label", "entity", "text", "value")
            for key in fallback_keys:
                if key in value:
                    result.extend(_coerce_entity_values(value[key]))
                    extracted = True
            if not extracted:
                for item in value.values():
                    result.extend(_coerce_entity_values(item))
        return result
    if isinstance(value, list | tuple | set):
        for item in value:
            result.extend(_coerce_entity_values(item))
        return result
    return [str(value)]


def _normalize_entities_field(raw: Any) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = {"people": [], "organizations": [], "locations": []}

    if isinstance(raw, dict):
        for key, value in raw.items():
            bucket = _resolve_entity_bucket(key)
            if bucket:
                buckets[bucket].extend(_coerce_entity_values(value))
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                bucket = (
                    _resolve_entity_bucket(item.get("type"))
                    or _resolve_entity_bucket(item.get("category"))
                    or _resolve_entity_bucket(item.get("label"))
                    or _resolve_entity_bucket(item.get("group"))
                )
                buckets[bucket or "people"].extend(_coerce_entity_values(item))
            else:
                buckets["people"].extend(_coerce_entity_values(item))
    else:
        buckets["people"].extend(_coerce_entity_values(raw))

    return {
        key: _dedupe_case_insensitive(
            [val for val in buckets[key] if isinstance(val, str) and val.strip()]
        )
        for key in buckets
    }


def _clean_string_list(values: Any, *, limit: int | None = None) -> list[str]:
    if values is None:
        return []
    result: list[str] = []
    seen: set[str] = set()
    iterable: list[Any]
    if isinstance(values, list | tuple | set):
        iterable = list(values)
    else:
        iterable = [values]
    for item in iterable:
        text = str(item).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _shape_insights(raw: Any) -> dict[str, Any]:
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

    shaped["open_questions"] = _clean_string_list(raw.get("open_questions"))
    shaped["suggested_sources"] = _clean_string_list(raw.get("suggested_sources"))
    shaped["expansion_topics"] = _clean_string_list(raw.get("expansion_topics"))
    shaped["next_exploration"] = _clean_string_list(raw.get("next_exploration"))

    caution_value = str(raw.get("caution", "")).strip()
    shaped["caution"] = caution_value or None

    return shaped


def _normalize_field_names(payload: SummaryJSON) -> SummaryJSON:
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


def validate_and_shape_summary(payload: SummaryJSON) -> SummaryJSON:
    """Validate and shape a model-produced summary to the canonical contract.

    Applies caps, deduplication, and ensures required keys exist.
    This is a light implementation for the initial skeleton; extend with
    stricter validation or pydantic models as needed.
    """
    # Security: Validate input
    if not payload or not isinstance(payload, dict):
        raise ValueError("Summary payload must be a non-empty dictionary")

    # Security: Prevent extremely large payloads
    if len(str(payload)) > 100000:  # 100KB limit
        raise ValueError("Summary payload too large")

    # Normalize field names first
    normalized_payload = _normalize_field_names(payload)
    p: SummaryJSON = dict(normalized_payload)

    # Handle summary fields with fallback logic
    tldr = str(p.get("tldr", "")).strip()
    summary_250 = str(p.get("summary_250", "")).strip()
    summary_1000 = str(p.get("summary_1000", "")).strip()

    # If the model provided a generic summary field, treat it as the 1000-character slot
    if not summary_1000 and "summary" in normalized_payload:
        summary_1000 = str(normalized_payload.get("summary", "")).strip()

    # Backfill missing fields using progressively longer slots
    if not tldr and summary_1000:
        tldr = summary_1000
    if not summary_1000 and tldr:
        summary_1000 = tldr
    if not summary_250 and summary_1000:
        summary_250 = _cap_text(summary_1000, 250)
    if not summary_250 and tldr:
        summary_250 = _cap_text(tldr, 250)

    if not any((summary_250, summary_1000, tldr)):
        fallback_text = _summary_fallback_from_supporting_fields(normalized_payload)
        if not fallback_text:
            fallback_text = _summary_fallback_from_supporting_fields(p)
        if fallback_text:
            summary_1000 = _cap_text(fallback_text, 1000)
            summary_250 = _cap_text(summary_1000, 250)
            tldr = summary_1000

    # Enforce caps where appropriate
    summary_250 = _cap_text(summary_250, 250)
    summary_1000 = _cap_text(summary_1000, 1000)

    if not summary_1000 and summary_250:
        summary_1000 = summary_250

    if not tldr:
        tldr = summary_1000 or summary_250

    p["summary_250"] = summary_250
    p["summary_1000"] = summary_1000
    p["tldr"] = tldr

    p["key_ideas"] = [str(x).strip() for x in p.get("key_ideas", []) if str(x).strip()]
    p["topic_tags"] = _hash_tagify([str(x) for x in p.get("topic_tags", [])])

    p["entities"] = _normalize_entities_field(p.get("entities"))

    # numeric & nested fields
    ert = p.get("estimated_reading_time_min")
    try:
        p["estimated_reading_time_min"] = int(ert) if ert is not None else 0
    except Exception:
        p["estimated_reading_time_min"] = 0

    # key_stats normalize: keep only items with label and numeric value
    norm_stats: list[dict] = []
    for item in p.get("key_stats", []) or []:
        try:
            label = str(item.get("label", "")).strip()
            if not label:
                continue
            value_raw = item.get("value")
            value = float(value_raw)
            unit = item.get("unit")
            source_excerpt = item.get("source_excerpt")
            source_excerpt_value = str(source_excerpt) if source_excerpt is not None else None
            norm_stats.append(
                {
                    "label": label,
                    "value": value,
                    "unit": str(unit) if unit is not None else None,
                    "source_excerpt": source_excerpt_value,
                }
            )
        except Exception:
            continue
    p["key_stats"] = norm_stats
    p.setdefault("answered_questions", [])
    # readability: compute locally if libs available and fields empty
    rb = p.get("readability") or {}
    method = str(rb.get("method") or "Flesch-Kincaid")
    score_val = rb.get("score")
    level = rb.get("level")
    # Choose source: prefer TL;DR, fallback to summary_250
    read_src = p.get("tldr") or p.get("summary_1000") or p.get("summary_250") or ""
    if score_val is None or not _is_numeric(score_val) or float(score_val or 0.0) == 0.0:
        score = 0.0
        try:
            # Import locally to keep optional
            import spacy
            from textacy.text_stats import TextStats

            nlp = spacy.blank("en")
            if "sentencizer" not in nlp.pipe_names:
                nlp.add_pipe("sentencizer")
            doc = nlp(read_src)
            stats = TextStats(doc)
            score = float(getattr(stats, "flesch_reading_ease", 0.0))
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
    p.setdefault("seo_keywords", [])

    # keyterms: populate seo_keywords/topic_tags if missing (best-effort)
    if not p.get("seo_keywords") or not p.get("topic_tags"):
        try:  # pragma: no cover - optional heavy deps
            import spacy
            from textacy.extract.keyterms import sgrank

            nlp_kw = spacy.blank("en")
            if "sentencizer" not in nlp_kw.pipe_names:
                nlp_kw.add_pipe("sentencizer")
            doc_kw = nlp_kw(read_src)
            pairs = list(sgrank(doc_kw, topn=10))
            terms = [str(t) for (t, _kscore) in pairs if str(t).strip()]
            if not p.get("seo_keywords"):
                p["seo_keywords"] = terms[:10]
            if not p.get("topic_tags") and terms:
                p["topic_tags"] = _hash_tagify(terms)
        except Exception:
            pass

    # Handle new fields with defaults
    p.setdefault("metadata", {})
    p.setdefault("extractive_quotes", [])
    p.setdefault("highlights", [])
    p.setdefault("questions_answered", [])
    p.setdefault("categories", [])
    p.setdefault("topic_taxonomy", [])
    p.setdefault("hallucination_risk", "low")
    p.setdefault("confidence", 1.0)
    p.setdefault("forwarded_post_extras", None)
    p.setdefault("key_points_to_remember", [])
    p["insights"] = _shape_insights(p.get("insights"))

    # Validate and clean new fields
    if not isinstance(p["confidence"], int | float) or not (0.0 <= p["confidence"] <= 1.0):
        p["confidence"] = 1.0

    if p["hallucination_risk"] not in ["low", "med", "high"]:
        p["hallucination_risk"] = "low"

    # Clean lists
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
            # Handle legacy format or single strings - try to split on common patterns
            qa_str = str(qa).strip()
            if qa_str:
                # Look for patterns like "Q: ... A: ..." or "Question: ... Answer: ..."
                import re

                qa_patterns = [
                    r"Q:\s*(.+?)\s*A:\s*(.+)",
                    r"Question:\s*(.+?)\s*Answer:\s*(.+)",
                    r"(.+?)\?\s*(.+)",  # Question ending with ? followed by answer
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
                # If no pattern matched, treat as a question without answer
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
                    "score": float(tax.get("score", 0.0)) if _is_numeric(tax.get("score")) else 0.0,
                    "path": str(tax.get("path", "")).strip() or None,
                }
            )
    p["topic_taxonomy"] = clean_taxonomy

    # Optional strict validation via Pydantic
    if PydanticAvailable:
        try:
            model = SummaryModelT(**p)
            # Pydantic v2: model_dump; v1: dict
            if hasattr(model, "model_dump"):
                return model.model_dump()
            return model.dict()
        except Exception:
            return p
    return p


def get_summary_json_schema() -> dict[str, Any]:
    """Return a JSON Schema for the summary contract.

    Prefers exporting from Pydantic if available; falls back to a static schema.
    """

    def _enforce_no_additional_props(schema_obj: Any) -> Any:
        """Recursively enforce additionalProperties: false on all object schemas.

        Handles nested objects under properties, items, oneOf/anyOf/allOf, $defs/definitions.
        """
        if isinstance(schema_obj, dict):
            # If this dict describes an object type, set additionalProperties: false when absent
            if schema_obj.get("type") == "object":
                schema_obj.setdefault("additionalProperties", False)

            # Recurse common schema composition constructs
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
        """Recursively ensure every object declares required for all of its properties.

        Some providers (e.g., Azure) require that for any object with properties,
        the 'required' array must include every key listed under 'properties'.
        """
        if isinstance(schema_obj, dict):
            if schema_obj.get("type") == "object" and isinstance(
                schema_obj.get("properties"), dict
            ):
                prop_keys = list(schema_obj["properties"].keys())
                # Set or replace 'required' to include all keys (provider requirement)
                schema_obj["required"] = prop_keys

                # Recurse into nested property schemas
                for _, sub in list(schema_obj["properties"].items()):
                    _enforce_required_all(sub)

            # Recurse common schema composition constructs
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

    if PydanticAvailable:
        try:
            from .summary_schema import SummaryModel

            # Pydantic v2
            if hasattr(SummaryModel, "model_json_schema"):
                schema = SummaryModel.model_json_schema()
            else:  # v1
                schema = SummaryModel.schema()

            # Ensure top-level is object and provider strictness is satisfied
            if isinstance(schema, dict):
                schema.setdefault("$schema", "http://json-schema.org/draft-07/schema#")
                schema.setdefault("type", "object")
                _enforce_no_additional_props(schema)
                _enforce_required_all(schema)
                return schema
        except Exception:
            pass

    # Static fallback schema
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary_250": {"type": "string", "maxLength": 250},
            "summary_1000": {"type": "string", "maxLength": 1000},
            "tldr": {"type": "string"},
            "key_ideas": {"type": "array", "items": {"type": "string"}},
            "topic_tags": {"type": "array", "items": {"type": "string"}},
            "entities": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "people": {"type": "array", "items": {"type": "string"}},
                    "organizations": {"type": "array", "items": {"type": "string"}},
                    "locations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["people", "organizations", "locations"],
            },
            "estimated_reading_time_min": {"type": "integer", "minimum": 0},
            "key_stats": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "number"},
                        "unit": {"type": ["string", "null"]},
                        "source_excerpt": {"type": ["string", "null"]},
                    },
                    "required": ["label", "value", "unit", "source_excerpt"],
                },
            },
            "answered_questions": {"type": "array", "items": {"type": "string"}},
            "readability": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "method": {"type": "string"},
                    "score": {"type": "number"},
                    "level": {"type": "string"},
                },
                "required": ["method", "score", "level"],
            },
            "seo_keywords": {"type": "array", "items": {"type": "string"}},
            "metadata": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": ["string", "null"]},
                    "canonical_url": {"type": ["string", "null"]},
                    "domain": {"type": ["string", "null"]},
                    "author": {"type": ["string", "null"]},
                    "published_at": {"type": ["string", "null"]},
                    "last_updated": {"type": ["string", "null"]},
                },
                "required": [
                    "title",
                    "canonical_url",
                    "domain",
                    "author",
                    "published_at",
                    "last_updated",
                ],
            },
            "extractive_quotes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "text": {"type": "string"},
                        "source_span": {"type": ["string", "null"]},
                    },
                    "required": ["text", "source_span"],
                },
            },
            "highlights": {"type": "array", "items": {"type": "string"}},
            "questions_answered": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                    },
                    "required": ["question", "answer"],
                },
            },
            "categories": {"type": "array", "items": {"type": "string"}},
            "topic_taxonomy": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string"},
                        "score": {"type": "number", "minimum": 0, "maximum": 1},
                        "path": {"type": ["string", "null"]},
                    },
                    "required": ["label", "score", "path"],
                },
            },
            "hallucination_risk": {"type": "string", "enum": ["low", "med", "high"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "forwarded_post_extras": {
                "type": ["object", "null"],
                "additionalProperties": False,
                "properties": {
                    "channel_id": {"type": ["integer", "null"]},
                    "channel_title": {"type": ["string", "null"]},
                    "channel_username": {"type": ["string", "null"]},
                    "message_id": {"type": ["integer", "null"]},
                    "post_datetime": {"type": ["string", "null"]},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "mentions": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "channel_id",
                    "channel_title",
                    "channel_username",
                    "message_id",
                    "post_datetime",
                    "hashtags",
                    "mentions",
                ],
            },
            "key_points_to_remember": {"type": "array", "items": {"type": "string"}},
            "insights": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "topic_overview": {"type": "string"},
                    "new_facts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "fact": {"type": "string"},
                                "why_it_matters": {"type": ["string", "null"]},
                                "source_hint": {"type": ["string", "null"]},
                                "confidence": {"type": ["number", "string", "null"]},
                            },
                            "required": ["fact", "why_it_matters", "source_hint", "confidence"],
                        },
                    },
                    "open_questions": {"type": "array", "items": {"type": "string"}},
                    "suggested_sources": {"type": "array", "items": {"type": "string"}},
                    "expansion_topics": {"type": "array", "items": {"type": "string"}},
                    "next_exploration": {"type": "array", "items": {"type": "string"}},
                    "caution": {"type": ["string", "null"]},
                },
                "required": [
                    "topic_overview",
                    "new_facts",
                    "open_questions",
                    "suggested_sources",
                    "expansion_topics",
                    "next_exploration",
                    "caution",
                ],
            },
        },
        "required": [
            "summary_250",
            "summary_1000",
            "tldr",
            "key_ideas",
            "topic_tags",
            "entities",
            "estimated_reading_time_min",
            "key_stats",
            "answered_questions",
            "readability",
            "seo_keywords",
            "metadata",
            "extractive_quotes",
            "highlights",
            "questions_answered",
            "categories",
            "topic_taxonomy",
            "hallucination_risk",
            "confidence",
            "forwarded_post_extras",
            "key_points_to_remember",
            "insights",
        ],
    }

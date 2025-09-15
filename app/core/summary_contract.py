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


def _normalize_field_names(payload: SummaryJSON) -> SummaryJSON:
    """Normalize field names from camelCase to snake_case.

    Handles common field name variations that LLMs might return.
    """
    field_mapping = {
        # Summary fields
        "summary250": "summary_250",
        "summary1000": "summary_1000",
        "summary_250": "summary_250",  # Already correct
        "summary_1000": "summary_1000",  # Already correct
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

    p["summary_250"] = _cap_text(str(p.get("summary_250", "")).strip(), 250)
    p["summary_1000"] = _cap_text(str(p.get("summary_1000", "")).strip(), 1000)

    p["key_ideas"] = [str(x).strip() for x in p.get("key_ideas", []) if str(x).strip()]
    p["topic_tags"] = _hash_tagify([str(x) for x in p.get("topic_tags", [])])

    entities = p.get("entities", {}) or {}
    entities["people"] = _dedupe_case_insensitive([str(x) for x in entities.get("people", [])])
    entities["organizations"] = _dedupe_case_insensitive(
        [str(x) for x in entities.get("organizations", [])]
    )
    entities["locations"] = _dedupe_case_insensitive(
        [str(x) for x in entities.get("locations", [])]
    )
    p["entities"] = entities

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
    # Choose source: prefer summary_1000, fallback to summary_250
    read_src = p.get("summary_1000") or p.get("summary_250") or ""
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
        },
        "required": [
            "summary_250",
            "summary_1000",
            "key_ideas",
            "topic_tags",
            "entities",
            "estimated_reading_time_min",
            "key_stats",
            "answered_questions",
            "readability",
            "seo_keywords",
        ],
    }

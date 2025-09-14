from __future__ import annotations

from typing import Any

from .summary_schema import PydanticAvailable

if PydanticAvailable:  # type: ignore
    from .summary_schema import SummaryModel  # noqa: F401


SummaryJSON = dict[str, Any]


def _cap_text(text: str, limit: int) -> str:
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
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        t = t.strip()
        if not t:
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
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        key = it.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(it.strip())
    return out


def validate_and_shape_summary(payload: SummaryJSON) -> SummaryJSON:
    """Validate and shape a model-produced summary to the canonical contract.

    Applies caps, deduplication, and ensures required keys exist.
    This is a light implementation for the initial skeleton; extend with
    stricter validation or pydantic models as needed.
    """
    p: SummaryJSON = dict(payload)

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
            norm_stats.append(
                {
                    "label": label,
                    "value": value,
                    "unit": str(unit) if unit is not None else None,
                    "source_excerpt": str(source_excerpt) if source_excerpt is not None else None,
                }
            )
        except Exception:
            continue
    p["key_stats"] = norm_stats
    p.setdefault("answered_questions", [])
    # readability
    rb = p.get("readability") or {}
    try:
        score = float(rb.get("score", 0.0))
    except Exception:
        score = 0.0
    level = rb.get("level")
    if not level:
        # simple mapping
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
        "method": str(rb.get("method") or "Flesch-Kincaid"),
        "score": score,
        "level": level,
    }
    p.setdefault("seo_keywords", [])

    # Optional strict validation via Pydantic
    if PydanticAvailable:
        try:
            model = SummaryModel(**p)  # type: ignore[name-defined]
            return model.model_dump()  # type: ignore[attr-defined]
        except Exception:
            # If pydantic fails, return shaped payload (still reasonably strict)
            return p
    else:
        return p

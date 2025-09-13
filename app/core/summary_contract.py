from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SummaryJSON = Dict[str, Any]


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


def _hash_tagify(tags: List[str], max_tags: int = 10) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
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


def _dedupe_case_insensitive(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
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
    entities["organizations"] = _dedupe_case_insensitive([str(x) for x in entities.get("organizations", [])])
    entities["locations"] = _dedupe_case_insensitive([str(x) for x in entities.get("locations", [])])
    p["entities"] = entities

    # numeric & nested fields
    ert = p.get("estimated_reading_time_min")
    try:
        p["estimated_reading_time_min"] = int(ert) if ert is not None else 0
    except Exception:
        p["estimated_reading_time_min"] = 0

    p.setdefault("key_stats", [])
    p.setdefault("answered_questions", [])
    p.setdefault("readability", {"method": "Flesch-Kincaid", "score": 0.0, "level": "Unknown"})
    p.setdefault("seo_keywords", [])

    return p


from __future__ import annotations

from typing import Any


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
            "key_ideas": [],
            "topic_tags": [],
            "entities": {"people": [], "organizations": [], "locations": []},
            "estimated_reading_time_min": 0,
            "key_stats": [],
            "answered_questions": [],
            "readability": {"method": "Flesch-Kincaid", "score": 0.0, "level": "Unknown"},
            "seo_keywords": [],
        }

    # Collect
    s250_parts: list[str] = []
    s1k_parts: list[str] = []
    key_ideas: list[str] = []
    topic_tags: list[str] = []
    entities: dict[str, list[str]] = {"people": [], "organizations": [], "locations": []}
    ert_sum = 0
    key_stats: list[dict[str, Any]] = []
    answered: list[str] = []
    seo_keywords: list[str] = []

    for s in summaries:
        try:
            s250 = str(s.get("summary_250", "")).strip()
            if s250:
                s250_parts.append(s250)
            s1k = str(s.get("summary_1000", "")).strip()
            if s1k:
                s1k_parts.append(s1k)
            key_ideas.extend([str(x) for x in (s.get("key_ideas") or [])])
            topic_tags.extend([str(x) for x in (s.get("topic_tags") or [])])
            entities = _merge_entities(entities, s.get("entities") or {})
            try:
                ert_sum += int(s.get("estimated_reading_time_min") or 0)
            except Exception:
                pass
            key_stats = _merge_key_stats(key_stats, s.get("key_stats") or [])
            answered.extend([str(x) for x in (s.get("answered_questions") or [])])
            seo_keywords.extend([str(x) for x in (s.get("seo_keywords") or [])])
        except Exception:
            continue

    # Build final
    s250_joined = "; ".join(_dedupe_list(s250_parts))
    s1k_joined = "\n".join(_dedupe_list(s1k_parts))
    return {
        "summary_250": s250_joined,
        "summary_1000": s1k_joined or s250_joined,
        "key_ideas": _dedupe_list(key_ideas, limit=10),
        "topic_tags": _dedupe_list(topic_tags, limit=8),
        "entities": entities,
        "estimated_reading_time_min": max(0, ert_sum),
        "key_stats": key_stats,
        "answered_questions": _dedupe_list(answered),
        "readability": {"method": "Flesch-Kincaid", "score": 0.0, "level": "Unknown"},
        "seo_keywords": _dedupe_list(seo_keywords, limit=15),
    }

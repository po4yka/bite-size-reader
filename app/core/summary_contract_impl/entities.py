from __future__ import annotations

from typing import Any

from app.core.summary_text_utils import dedupe_case_insensitive as _dedupe_case_insensitive

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
    if name is None:
        return None
    normalized = str(name).strip().lower()
    if not normalized:
        return None
    bucket = _ENTITY_KEY_ALIASES.get(normalized, normalized)
    return bucket if bucket in {"people", "organizations", "locations"} else None


def coerce_entity_values(value: Any) -> list[str]:
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
        key: _dedupe_case_insensitive(
            [val for val in buckets[key] if isinstance(val, str) and val.strip()]
        )
        for key in buckets
    }

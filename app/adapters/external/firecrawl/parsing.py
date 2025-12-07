from __future__ import annotations

from typing import Any

from app.adapters.external.firecrawl.models import FirecrawlSearchItem


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        value = str(value)
    text = str(value).strip()
    return text or None


def extract_total_results(payload: Any) -> int | None:
    queue: list[Any] = [payload]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))

        if isinstance(current, dict):
            for key in ("totalResults", "total_results", "numResults", "total"):
                value = current.get(key)
                if isinstance(value, int) and value >= 0:
                    return value
            nested = current.get("data")
            if nested is not None:
                queue.append(nested)
        elif isinstance(current, list):
            queue.extend(current)
    return None


def extract_error_message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("error", "message"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = payload.get("data")
        if nested is not None:
            nested_error = extract_error_message(nested)
            if nested_error:
                return nested_error
    elif isinstance(payload, list):
        for item in payload:
            nested_error = extract_error_message(item)
            if nested_error:
                return nested_error
    return None


def has_url_field(item: dict[str, Any]) -> bool:
    url_value = item.get("url") or item.get("link") or item.get("sourceUrl")
    return bool(isinstance(url_value, str) and url_value.strip())


def extract_result_items(payload: Any) -> list[dict[str, Any]]:
    queue: list[Any] = [payload]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))

        if isinstance(current, list):
            dict_items = [item for item in current if isinstance(item, dict)]
            url_items = [item for item in dict_items if has_url_field(item)]
            if url_items:
                return url_items
            queue.extend(current)
        elif isinstance(current, dict):
            if has_url_field(current):
                return [current]
            for key in ("results", "items", "data", "matches"):
                if key in current:
                    queue.append(current[key])
    return []


def normalize_search_item(raw: dict[str, Any]) -> FirecrawlSearchItem | None:
    url = normalize_text(
        raw.get("url") or raw.get("link") or raw.get("sourceUrl") or raw.get("permalink")
    )
    if not url:
        return None

    title = normalize_text(raw.get("title") or raw.get("name") or raw.get("headline")) or url

    snippet_source = (
        raw.get("snippet") or raw.get("description") or raw.get("summary") or raw.get("content")
    )
    snippet = normalize_text(snippet_source)
    if snippet:
        snippet = " ".join(snippet.split())

    source_value: Any = raw.get("source") or raw.get("site") or raw.get("publisher")
    if isinstance(source_value, dict):
        source_value = source_value.get("name") or source_value.get("title")
    elif isinstance(source_value, list):
        parts = [normalize_text(part) for part in source_value]
        source_value = ", ".join(part for part in parts if part)
    source = normalize_text(source_value)

    published_raw = (
        raw.get("published_at") or raw.get("publishedAt") or raw.get("published") or raw.get("date")
    )
    if isinstance(published_raw, dict):
        published_raw = published_raw.get("iso") or published_raw.get("value")
    published = normalize_text(published_raw)

    return FirecrawlSearchItem(
        title=title,
        url=url,
        snippet=snippet,
        source=source,
        published_at=published,
    )

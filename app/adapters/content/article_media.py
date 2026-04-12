"""Utilities for selecting article image candidates for multimodal summarization."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.application.dto.aggregation import SourceMediaAsset, SourceMediaKind

if TYPE_CHECKING:
    from app.adapters.external.firecrawl.models import FirecrawlResult

_MARKDOWN_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((https?://[^\s\)]+)\)")
_DECORATIVE_PATH_TERMS = (
    "logo",
    "icon",
    "favicon",
    "avatar",
    "sprite",
    "placeholder",
    "pixel",
    "tracker",
    "tracking",
    "badge",
    "emoji",
)
_DECORATIVE_ALT_TERMS = (
    "logo",
    "icon",
    "avatar",
    "profile picture",
    "tracking pixel",
    "decorative",
)
_TRACKING_HOST_TERMS = (
    "doubleclick",
    "google-analytics",
    "facebook.com/tr",
    "facebook.net",
    "googletagmanager",
)
_BLOCKED_EXTENSIONS = (".svg", ".ico")


def extract_firecrawl_image_assets(
    crawl: FirecrawlResult | Any,
    *,
    max_assets: int = 5,
) -> tuple[list[SourceMediaAsset], dict[str, Any]]:
    """Extract and quality-filter image candidates from Firecrawl output."""

    candidates = _collect_firecrawl_image_candidates(crawl)
    selected: list[SourceMediaAsset] = []
    rejected_counts: dict[str, int] = {}
    best_by_url: dict[str, SourceMediaAsset] = {}

    for candidate in candidates:
        url = str(candidate.get("url") or "").strip()
        if not url:
            _increment(rejected_counts, "missing_url")
            continue
        allowed, reason = _is_content_image_candidate(candidate)
        if not allowed:
            _increment(rejected_counts, reason)
            continue

        asset = SourceMediaAsset(
            kind=SourceMediaKind.IMAGE,
            url=url,
            alt_text=_clean_text(candidate.get("alt_text")),
            mime_type=_clean_text(candidate.get("mime_type")),
            metadata={
                "source": candidate.get("source"),
                "source_key": candidate.get("source_key"),
                "width": candidate.get("width"),
                "height": candidate.get("height"),
            },
        )
        existing = best_by_url.get(url)
        if existing is None or (not existing.alt_text and asset.alt_text):
            best_by_url[url] = asset

    for asset in best_by_url.values():
        if len(selected) >= max_assets:
            _increment(rejected_counts, "max_assets")
            continue
        selected.append(asset.model_copy(update={"position": len(selected)}))

    report = {
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "rejected_count": max(0, len(candidates) - len(selected)),
        "rejected_reasons": rejected_counts,
        "strategy": "firecrawl_metadata_and_markdown",
    }
    return selected, report


def _collect_firecrawl_image_candidates(crawl: FirecrawlResult | Any) -> list[dict[str, Any]]:
    raw_metadata = getattr(crawl, "metadata_json", None)
    metadata_json = raw_metadata if isinstance(raw_metadata, dict) else {}
    candidates: list[dict[str, Any]] = []

    for key in ("images", "image_urls", "thumbnails", "screenshots"):
        candidates.extend(_coerce_candidates(metadata_json.get(key), source_key=key))
    for key in ("image", "image_url", "og:image", "ogImage"):
        candidates.extend(_coerce_candidates(metadata_json.get(key), source_key=key))

    content_markdown = getattr(crawl, "content_markdown", None)
    if content_markdown:
        for alt_text, url in _MARKDOWN_IMAGE_RE.findall(content_markdown):
            candidates.append(
                {
                    "url": url.strip(),
                    "alt_text": alt_text.strip() or None,
                    "source": "markdown",
                    "source_key": "markdown_image",
                }
            )

    return candidates


def _coerce_candidates(value: Any, *, source_key: str) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else [value]
    candidates: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            candidates.append(
                {
                    "url": item.strip(),
                    "source": "firecrawl_metadata",
                    "source_key": source_key,
                }
            )
            continue
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "url": _clean_text(
                    item.get("url") or item.get("src") or item.get("image") or item.get("image_url")
                ),
                "alt_text": _clean_text(item.get("alt") or item.get("alt_text")),
                "mime_type": _clean_text(item.get("mime_type") or item.get("content_type")),
                "width": _coerce_int(item.get("width")),
                "height": _coerce_int(item.get("height")),
                "source": "firecrawl_metadata",
                "source_key": source_key,
            }
        )
    return candidates


def _is_content_image_candidate(candidate: dict[str, Any]) -> tuple[bool, str]:
    url = str(candidate.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False, "non_http"

    lower_url = url.lower()
    if any(term in lower_url for term in _TRACKING_HOST_TERMS):
        return False, "tracking_host"
    if parsed.path.lower().endswith(_BLOCKED_EXTENSIONS):
        return False, "blocked_extension"

    path_and_query = f"{parsed.path}?{parsed.query}".lower()
    if any(term in path_and_query for term in _DECORATIVE_PATH_TERMS):
        return False, "decorative_path"

    alt_text = _clean_text(candidate.get("alt_text"))
    if alt_text and any(term in alt_text.lower() for term in _DECORATIVE_ALT_TERMS):
        return False, "decorative_alt"

    width = _coerce_int(candidate.get("width"))
    height = _coerce_int(candidate.get("height"))
    if width is not None and height is not None and width <= 96 and height <= 96:
        return False, "tiny_dimensions"

    return True, "ok"


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

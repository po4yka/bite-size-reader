from __future__ import annotations

import hashlib
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
}


_URL_SEARCH_PATTERN = re.compile(r"https?://[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
_URL_FINDALL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_DANGEROUS_URL_SUBSTRINGS: tuple[str, ...] = (
    "<",
    ">",
    '"',
    "'",
    "script",
    "javascript:",
    "data:",
)


def _validate_url_input(url: str) -> None:
    """Validate URL input for security."""
    if not url:
        raise ValueError("URL cannot be empty")
    if not isinstance(url, str):
        raise ValueError("URL must be a string")
    if len(url) > 2048:  # RFC 2616 limit
        raise ValueError("URL too long")
    # Basic security: no obvious injection attempts
    url_lower = url.lower()
    if any(needle in url_lower for needle in _DANGEROUS_URL_SUBSTRINGS):
        raise ValueError("URL contains potentially dangerous content")


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication as per SPEC.md.

    - Lowercase scheme & host
    - Strip fragment
    - Sort query params and remove common tracking params
    - Collapse trailing slash
    """
    _validate_url_input(url)

    # Add protocol if missing
    if "://" not in url:
        url = f"http://{url}"

    try:
        p = urlparse(url)

        # Validate parsed components
        if not p.netloc:
            raise ValueError("Invalid URL: missing hostname")

        # Security: validate scheme
        if p.scheme and p.scheme.lower() not in {"http", "https"}:
            raise ValueError(f"Unsupported URL scheme: {p.scheme}")

        scheme = (p.scheme or "http").lower()
        netloc = p.netloc.lower()
        path = p.path or "/"

        # Remove redundant trailing slash except for root
        if path.endswith("/") and path != "/":
            path = path.rstrip("/")

        # Filter and sort query params
        query_pairs = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        query_pairs.sort(key=lambda x: (x[0], x[1]))
        query = urlencode(query_pairs)

        normalized = urlunparse((scheme, netloc, path, "", query, ""))
        logger.debug("normalize_url", extra={"url": url[:100], "normalized": normalized[:100]})
        return normalized
    except Exception as e:
        logger.error("url_normalization_failed", extra={"url": url[:100], "error": str(e)})
        raise ValueError(f"URL normalization failed: {e}") from e


def url_hash_sha256(normalized_url: str) -> str:
    """Generate SHA256 hash of normalized URL."""
    if not normalized_url or not isinstance(normalized_url, str):
        raise ValueError("Normalized URL is required")
    if len(normalized_url) > 2048:
        raise ValueError("Normalized URL too long")

    try:
        h = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()
        logger.debug("url_hash", extra={"normalized": normalized_url[:100], "sha256": h})
        return h
    except Exception as e:
        logger.error("url_hash_failed", extra={"error": str(e)})
        raise ValueError(f"URL hashing failed: {e}") from e


def looks_like_url(text: str) -> bool:
    """Check if text contains what looks like a URL."""
    if not text or not isinstance(text, str):
        return False
    if len(text) > 10000:  # Prevent processing of extremely long text
        return False

    try:
        ok = bool(_URL_SEARCH_PATTERN.search(text))
        logger.debug("looks_like_url", extra={"text_sample": text[:80], "match": ok})
        return ok
    except Exception as e:
        logger.error("looks_like_url_failed", extra={"error": str(e)})
        return False


def extract_first_url(text: str) -> str | None:
    """Extract the first URL from text."""
    if not text or not isinstance(text, str):
        return None
    if len(text) > 10000:  # Prevent processing of extremely long text
        return None

    try:
        m = _URL_SEARCH_PATTERN.search(text)
        val = m.group(0) if m else None
        logger.debug(
            "extract_first_url", extra={"text_sample": text[:80], "url": val[:100] if val else None}
        )
        return val
    except Exception as e:
        logger.error("extract_first_url_failed", extra={"error": str(e)})
        return None


def extract_all_urls(text: str) -> list[str]:
    """Extract all URLs from text with optimized performance."""
    if not text or not isinstance(text, str):
        return []
    if len(text) > 10000:  # Prevent processing of extremely long text
        return []

    try:
        # Optimized regex pattern for better performance
        urls = _URL_FINDALL_PATTERN.findall(text)

        if not urls:
            return []

        # Validate and filter URLs with early exit optimization
        valid_urls = []
        seen = set()  # Combine deduplication with validation

        for url in urls:
            # Skip if already seen (deduplication)
            if url in seen:
                continue

            try:
                _validate_url_input(url)
                valid_urls.append(url)
                seen.add(url)
            except ValueError:
                # Skip invalid URLs silently for performance
                continue

        logger.debug("extract_all_urls", extra={"count": len(valid_urls), "input_len": len(text)})
        return valid_urls
    except Exception as e:
        logger.error("extract_all_urls_failed", extra={"error": str(e)})
        return []

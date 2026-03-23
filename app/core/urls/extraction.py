from __future__ import annotations

import re

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

_URL_SEARCH_PATTERN = re.compile(r"https?://[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
_URL_FINDALL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_WWW_URL_SEARCH_PATTERN = re.compile(r"\bwww\.[\w\.-]+[\w\./\-?=&%#]*", re.IGNORECASE)
_WWW_URL_FINDALL_PATTERN = re.compile(r"\bwww\.[\w\.-]+[^\s<>\"']*", re.IGNORECASE)


def looks_like_url(text: str, max_text_length_kb: int = 50) -> bool:
    """Check if text contains what looks like a URL."""
    if not text or not isinstance(text, str):
        return False

    max_text_length = max_text_length_kb * 1024
    if len(text) > max_text_length:
        logger.warning(
            "looks_like_url_text_too_long",
            extra={"text_length": len(text), "max_allowed": max_text_length},
        )
        return False

    try:
        looks_like = bool(_URL_SEARCH_PATTERN.search(text))
        if not looks_like:
            looks_like = bool(_WWW_URL_SEARCH_PATTERN.search(text))
        logger.debug("looks_like_url", extra={"text_sample": text[:80], "match": looks_like})
        return looks_like
    except Exception as exc:
        logger.exception("looks_like_url_failed", extra={"error": str(exc)})
        return False


def extract_all_urls(text: str, max_text_length_kb: int = 50) -> list[str]:
    """Extract all URLs from text with optimized performance."""
    if not text or not isinstance(text, str):
        return []

    max_text_length = max_text_length_kb * 1024
    if len(text) > max_text_length:
        logger.warning(
            "extract_all_urls_text_too_long",
            extra={"text_length": len(text), "max_allowed": max_text_length},
        )
        return []

    try:
        urls = _URL_FINDALL_PATTERN.findall(text)
        www_urls = _WWW_URL_FINDALL_PATTERN.findall(text)

        valid_urls: list[str] = []
        seen: set[str] = set()

        for url in urls:
            if url in seen:
                continue
            valid_urls.append(url)
            seen.add(url)

        for url in www_urls:
            normalized_url = f"https://{url}"
            if normalized_url in seen or url in seen:
                continue
            valid_urls.append(normalized_url)
            seen.add(normalized_url)

        logger.debug("extract_all_urls", extra={"count": len(valid_urls), "input_len": len(text)})
        return valid_urls
    except Exception as exc:
        logger.exception("extract_all_urls_failed", extra={"error": str(exc)})
        return []


__all__ = [
    "extract_all_urls",
    "looks_like_url",
]

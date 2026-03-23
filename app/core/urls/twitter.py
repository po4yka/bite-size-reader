from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.logging_utils import get_logger

logger = get_logger(__name__)

_TWITTER_HOSTS: frozenset[str] = frozenset(
    {
        "x.com",
        "twitter.com",
        "www.x.com",
        "www.twitter.com",
        "mobile.x.com",
        "mobile.twitter.com",
    }
)
_TWEET_STATUS_PATH_RE = re.compile(
    r"^/(?P<user>[^/]+)/status/(?P<id>\d+)(?:/.*)?$",
    re.IGNORECASE,
)
_TWEET_I_WEB_STATUS_PATH_RE = re.compile(r"^/i/web/status/(?P<id>\d+)(?:/.*)?$", re.IGNORECASE)
_ARTICLE_PATH_RE = re.compile(r"^/i/article/(?P<id>\d+)(?:/.*)?$", re.IGNORECASE)


def _parse_twitter_url_host_path(url: str) -> tuple[str, str] | None:
    """Parse a URL and return normalized ``(host, path)`` for Twitter matching."""
    if not url or not isinstance(url, str):
        return None
    candidate = url.strip()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    path = (parsed.path or "/").rstrip("/") or "/"
    return host, path


def is_twitter_url(url: str) -> bool:
    """Check if URL is a Twitter/X tweet or article."""
    try:
        return extract_tweet_id(url) is not None or extract_twitter_article_id(url) is not None
    except Exception as exc:
        logger.exception("is_twitter_url_failed", extra={"error": str(exc), "url": url[:100]})
        return False


def extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from a Twitter/X status URL."""
    tweet_id = extract_twitter_status_id(url)
    if tweet_id:
        return tweet_id
    parts = extract_twitter_status_parts(url)
    return parts[1] if parts else None


def extract_twitter_status_parts(url: str) -> tuple[str, str] | None:
    """Extract ``(username, tweet_id)`` from a Twitter/X status URL."""
    try:
        parsed = _parse_twitter_url_host_path(url)
        if not parsed:
            return None
        host, path = parsed
        if host not in _TWITTER_HOSTS:
            return None
        match = _TWEET_STATUS_PATH_RE.match(path)
        if match:
            return match.group("user"), match.group("id")
        return None
    except Exception as exc:
        logger.exception(
            "extract_twitter_status_parts_failed",
            extra={"error": str(exc), "url": url[:100]},
        )
        return None


def extract_twitter_status_id(url: str) -> str | None:
    """Extract tweet ID from a Twitter/X status URL."""
    if not url or not isinstance(url, str):
        return None
    try:
        parts = extract_twitter_status_parts(url)
        if parts:
            return parts[1]
        parsed = _parse_twitter_url_host_path(url)
        if not parsed:
            return None
        host, path = parsed
        if host not in _TWITTER_HOSTS:
            return None
        match = _TWEET_I_WEB_STATUS_PATH_RE.match(path)
        return match.group("id") if match else None
    except Exception:
        return None


def extract_twitter_article_id(url: str) -> str | None:
    """Extract article ID from an X/Twitter article URL."""
    try:
        parsed = _parse_twitter_url_host_path(url)
        if not parsed:
            return None
        host, path = parsed
        if host not in _TWITTER_HOSTS:
            return None
        match = _ARTICLE_PATH_RE.match(path)
        return match.group("id") if match else None
    except Exception:
        return None


def canonicalize_twitter_url(url: str) -> str | None:
    """Canonicalize supported Twitter/X URLs for stable dedupe hashing."""
    tweet_id = extract_twitter_status_id(url)
    if tweet_id:
        return f"https://x.com/i/web/status/{tweet_id}"

    article_id = extract_twitter_article_id(url)
    if article_id:
        return f"https://x.com/i/article/{article_id}"

    return None


def is_twitter_article_url(url: str) -> bool:
    """Check if URL points to an X Article."""
    return extract_twitter_article_id(url) is not None


__all__ = [
    "canonicalize_twitter_url",
    "extract_tweet_id",
    "extract_twitter_article_id",
    "extract_twitter_status_id",
    "extract_twitter_status_parts",
    "is_twitter_article_url",
    "is_twitter_url",
]

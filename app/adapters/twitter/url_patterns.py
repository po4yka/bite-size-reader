"""Detailed URL parsing for Twitter/X URLs.

Handles tweet status URLs, article URLs, and t.co short URL resolution.
"""

from __future__ import annotations

import re

_TWEET_URL_RE = re.compile(
    r"https?://(?:(?:www|mobile)\.)?(?:x|twitter)\.com/"
    r"(?P<user>[^/]+)/status/(?P<id>\d+)"
)

_ARTICLE_URL_RE = re.compile(
    r"https?://(?:(?:www|mobile)\.)?(?:x|twitter)\.com/i/article/(?P<id>\d+)"
)


def parse_tweet_url(url: str) -> tuple[str, str]:
    """Extract (username, tweet_id) from an X/Twitter status URL.

    Args:
        url: Full tweet URL

    Returns:
        Tuple of (username, tweet_id)

    Raises:
        ValueError: If URL is not a valid tweet URL
    """
    m = _TWEET_URL_RE.match(url.split("?", maxsplit=1)[0].rstrip("/"))
    if not m:
        msg = f"Not a valid tweet URL: {url}"
        raise ValueError(msg)
    return m.group("user"), m.group("id")


def parse_article_url(url: str) -> str | None:
    """Extract article_id from an X Article URL.

    Args:
        url: Full article URL

    Returns:
        Article ID string, or None if not an article URL
    """
    m = _ARTICLE_URL_RE.match(url.split("?", maxsplit=1)[0].rstrip("/"))
    return m.group("id") if m else None

"""Detailed URL parsing for Twitter/X URLs.

Handles tweet status URLs, article URLs, and t.co short URL resolution.
"""

from __future__ import annotations

from app.core.url_utils import extract_twitter_article_id, extract_twitter_status_parts


def parse_tweet_url(url: str) -> tuple[str, str]:
    """Extract (username, tweet_id) from an X/Twitter status URL.

    Args:
        url: Full tweet URL

    Returns:
        Tuple of (username, tweet_id)

    Raises:
        ValueError: If URL is not a valid tweet URL
    """
    parts = extract_twitter_status_parts(url)
    if not parts:
        msg = f"Not a valid tweet URL: {url}"
        raise ValueError(msg)
    return parts


def parse_article_url(url: str) -> str | None:
    """Extract article_id from an X Article URL.

    Args:
        url: Full article URL

    Returns:
        Article ID string, or None if not an article URL
    """
    return extract_twitter_article_id(url)

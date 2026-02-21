"""Format extracted Twitter/X data into clean text for LLM summarization.

Pure functions -- no I/O or side effects.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.adapters.twitter.graphql_parser import TweetData

# t.co URL pattern for stripping/replacement
_TCO_RE = re.compile(r"https?://t\.co/\S+")


def format_tweets_for_summary(tweets: list[TweetData]) -> str:
    """Format a list of tweets into clean, LLM-ready text.

    For single tweets, returns just the text. For threads, concatenates
    with attribution and numbering.

    Args:
        tweets: Ordered list of TweetData from extraction

    Returns:
        Formatted text string ready for summarization
    """
    if not tweets:
        return ""

    # Single tweet (no thread)
    if len(tweets) == 1:
        return _format_single_tweet(tweets[0])

    # Thread: concatenate with numbering
    parts: list[str] = []
    author = tweets[0].author or tweets[0].author_handle
    parts.append(f"Thread by @{tweets[0].author_handle} ({author}):\n")

    for i, tweet in enumerate(tweets, 1):
        text = _clean_tweet_text(tweet.text)
        parts.append(f"[{i}/{len(tweets)}] {text}")

        if tweet.quote_tweet:
            qt_text = _clean_tweet_text(tweet.quote_tweet.text)
            qt_handle = tweet.quote_tweet.author_handle
            parts.append(f"  > Quoting @{qt_handle}: {qt_text}")

    return "\n\n".join(parts)


def format_article_for_summary(article_data: dict[str, Any]) -> str:
    """Format X Article data into clean, LLM-ready text.

    Args:
        article_data: Dict with title, author, content keys

    Returns:
        Formatted text string ready for summarization
    """
    parts: list[str] = []

    title = article_data.get("title", "").strip()
    author = article_data.get("author", "").strip()
    content = article_data.get("content", "").strip()

    if title:
        parts.append(f"# {title}")
    if author:
        parts.append(f"By {author}")
    if title or author:
        parts.append("")  # blank line separator

    if content:
        # Clean up excessive whitespace from DOM scraping
        content = re.sub(r"\n{3,}", "\n\n", content)
        parts.append(content)

    return "\n".join(parts)


def _format_single_tweet(tweet: TweetData) -> str:
    """Format a single tweet with optional quote tweet."""
    parts: list[str] = []

    author = tweet.author or tweet.author_handle
    text = _clean_tweet_text(tweet.text)
    parts.append(f"@{tweet.author_handle} ({author}):\n{text}")

    if tweet.quote_tweet:
        qt_text = _clean_tweet_text(tweet.quote_tweet.text)
        qt_handle = tweet.quote_tweet.author_handle
        qt_author = tweet.quote_tweet.author or qt_handle
        parts.append(f"\nQuoting @{qt_handle} ({qt_author}):\n{qt_text}")

    return "\n".join(parts)


def _clean_tweet_text(text: str) -> str:
    """Clean tweet text for summarization.

    Strips t.co URLs (the full URLs are typically in the entities which
    we don't need for text summarization). Normalizes whitespace.
    """
    # Remove t.co URLs (they're just tracking redirects)
    text = _TCO_RE.sub("", text)
    # Normalize whitespace
    return re.sub(r"[ \t]+", " ", text).strip()

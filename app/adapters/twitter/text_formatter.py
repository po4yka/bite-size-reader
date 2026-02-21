"""Format extracted Twitter/X data into clean text for LLM summarization.

Pure functions -- no I/O or side effects.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.adapters.twitter.graphql_parser import TweetData

# ---------------------------------------------------------------------------
# Article header parsing (title/author from content text)
# ---------------------------------------------------------------------------

# Regex for metadata lines between header and body
_DATE_RE = re.compile(
    r"^(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}"
    r"|^\d{1,2}[hm]$"
    r"|^\d{4}$"
)
_ENGAGEMENT_RE = re.compile(r"^\d[\d,.]*[KkMm]?$")
_SKIP_KEYWORDS = {"Follow", "Subscribe", "Article", "Subscribed"}

# Titles that indicate DOM selectors missed the real title
BAD_TITLES = {"X", "Twitter", ""}


def parse_article_header(
    content: str,
) -> tuple[str, str, str, str]:
    """Extract title, author, handle, and body from raw article content text.

    X Article DOM scraping embeds the real title/author in the content text.
    Two patterns exist:

    Pattern A (title first -- most common):
        Title\\nAuthor Name\\n@handle\\n...metadata...\\nBody

    Pattern B (author first -- rare):
        Author Name\\n@handle\\n...metadata...\\n[Article]\\nTitle\\nBody

    Returns (title, author, author_handle, body).
    All returned strings are stripped; empty string if not found.
    """
    if not content or not content.strip():
        return ("", "", "", content or "")

    lines = content.split("\n")
    # Remove leading blank lines
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ("", "", "", "")
    if len(lines) == 1:
        return (lines[0].strip(), "", "", lines[0].strip())

    # Discriminator: Pattern B if second line starts with @
    if lines[1].strip().startswith("@"):
        # Pattern B: author first
        author = lines[0].strip()
        author_handle = lines[1].strip().lstrip("@")
        title = ""
        body_start = 2
        for i in range(2, min(len(lines), 15)):
            line = lines[i].strip()
            if not line:
                continue
            if line in _SKIP_KEYWORDS:
                continue
            if line == "\u00b7" or len(line) == 1:
                continue
            if _DATE_RE.match(line):
                continue
            if _ENGAGEMENT_RE.match(line):
                continue
            # First non-metadata line is the title
            title = line
            body_start = i + 1
            break
        body = "\n".join(lines[body_start:]).strip()
        return (title, author, author_handle, body)

    # Pattern A: title first (most common)
    title = lines[0].strip()
    author = lines[1].strip() if len(lines) > 1 else ""
    author_handle = ""
    body_start = 2
    # Line 2 should be @handle
    if len(lines) > 2 and lines[2].strip().startswith("@"):
        author_handle = lines[2].strip().lstrip("@")
        body_start = 3
    # Skip remaining metadata lines
    for i in range(body_start, min(len(lines), 20)):
        line = lines[i].strip()
        if not line:
            continue
        if line in _SKIP_KEYWORDS:
            continue
        if line == "\u00b7" or len(line) == 1:
            continue
        if _DATE_RE.match(line):
            continue
        if _ENGAGEMENT_RE.match(line):
            continue
        body_start = i
        break
    body = "\n".join(lines[body_start:]).strip()
    return (title, author, author_handle, body)


def _has_article_header(content: str) -> bool:
    """Check if content text looks like it has an X Article header with @handle."""
    if not content:
        return False
    lines = content.split("\n")
    return any(line.strip().startswith("@") for line in lines[:5])


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

    When DOM selectors miss the real title/author (returning "X" or ""),
    parses them from the content text header.

    Args:
        article_data: Dict with title, author, content keys

    Returns:
        Formatted text string ready for summarization
    """
    parts: list[str] = []

    title = article_data.get("title", "").strip()
    author = article_data.get("author", "").strip()
    content = article_data.get("content", "").strip()

    # Parse title/author from content when DOM selectors missed them.
    # Only attempt if content looks like it has an article header (contains @handle).
    if (title in BAD_TITLES or not author) and _has_article_header(content):
        parsed_title, parsed_author, _parsed_handle, parsed_body = parse_article_header(content)
        if title in BAD_TITLES and parsed_title:
            title = parsed_title
        if not author and parsed_author:
            author = parsed_author
        if parsed_body:
            content = parsed_body

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

    Preserves URLs (including t.co links) to avoid dropping key context from
    link-centric posts. Normalizes whitespace.
    """
    # Normalize whitespace
    return re.sub(r"[ \t]+", " ", text).strip()

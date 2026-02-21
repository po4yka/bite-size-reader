"""Parse X's GraphQL TweetDetail API responses into structured data.

Pure functions with no I/O -- suitable for unit testing with canned fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TweetData:
    """A single tweet's extracted content."""

    tweet_id: str
    author: str
    author_handle: str
    text: str
    images: list[str] = field(default_factory=list)
    quote_tweet: TweetData | None = None
    order: int = 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "tweet_id": self.tweet_id,
            "author": self.author,
            "author_handle": self.author_handle,
            "text": self.text,
            "images": self.images,
            "order": self.order,
        }
        if self.quote_tweet:
            d["quote_tweet"] = self.quote_tweet.to_dict()
        return d


@dataclass
class ExtractionResult:
    """Complete extraction output for a tweet URL."""

    url: str
    tweets: list[TweetData] = field(default_factory=list)
    article_data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "url": self.url,
            "tweets": [t.to_dict() for t in self.tweets],
        }
        if self.article_data:
            d["article_data"] = self.article_data
        return d


def extract_tweets_from_graphql(response_json: dict[str, Any]) -> list[TweetData]:
    """Parse X's TweetDetail GraphQL response into TweetData objects.

    Handles both the threaded_conversation_with_injections_v2 shape
    (thread view) and the single tweetResult shape (direct lookup).

    Args:
        response_json: Raw JSON response from X's GraphQL API

    Returns:
        List of TweetData objects, ordered by appearance
    """
    tweets: list[TweetData] = []
    try:
        data = response_json.get("data") or {}
        timeline = (data.get("threaded_conversation_with_injections_v2") or {}).get(
            "instructions", []
        )
        if timeline:
            order = 0
            for instruction in timeline:
                for entry in instruction.get("entries", []):
                    content = entry.get("content", {})
                    item_content = content.get("itemContent", {})
                    # Single tweet entry
                    if item_content.get("tweet_results", {}).get("result"):
                        tweet = _parse_single_tweet(item_content["tweet_results"]["result"], order)
                        if tweet:
                            tweets.append(tweet)
                            order += 1
                    # Conversation module (thread replies)
                    for item in content.get("items", []):
                        ic = item.get("item", {}).get("itemContent", {})
                        result = ic.get("tweet_results", {}).get("result")
                        if result:
                            tweet = _parse_single_tweet(result, order)
                            if tweet:
                                tweets.append(tweet)
                                order += 1
        else:
            # Fallback: single tweetResult shape
            result = (data.get("tweetResult") or {}).get("result")
            if result:
                tweet = _parse_single_tweet(result, 0)
                if tweet:
                    tweets.append(tweet)
    except (KeyError, TypeError):
        pass
    return tweets


def _parse_single_tweet(result: dict[str, Any], order: int) -> TweetData | None:
    """Extract a TweetData from a single tweet result node.

    Handles TweetWithVisibilityResults wrapper and quote tweet expansion.
    """
    # Unwrap TweetWithVisibilityResults wrapper
    if result.get("__typename") == "TweetWithVisibilityResults":
        result = result.get("tweet", result)

    legacy = result.get("legacy")
    if not legacy:
        return None

    core = result.get("core", {}).get("user_results", {}).get("result", {})
    user_legacy = core.get("legacy", {})

    author = user_legacy.get("name", "")
    author_handle = user_legacy.get("screen_name", "")
    tweet_id = legacy.get("id_str", result.get("rest_id", ""))
    text = legacy.get("full_text", "")

    # Extract image URLs
    images: list[str] = []
    media = legacy.get("extended_entities", {}).get("media", [])
    for m in media:
        if m.get("type") == "photo":
            url = m.get("media_url_https", "")
            if url:
                images.append(url)

    # Extract quote tweet
    quote_tweet = None
    qt_result = result.get("quoted_status_result", {}).get("result")
    if qt_result:
        quote_tweet = _parse_single_tweet(qt_result, 0)

    return TweetData(
        tweet_id=tweet_id,
        author=author,
        author_handle=author_handle,
        text=text,
        images=images,
        quote_tweet=quote_tweet,
        order=order,
    )

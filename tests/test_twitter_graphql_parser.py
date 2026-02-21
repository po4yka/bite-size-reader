"""Tests for Twitter/X GraphQL response parsing."""

from __future__ import annotations

from app.adapters.twitter.graphql_parser import (
    ExtractionResult,
    TweetData,
    extract_tweets_from_graphql,
)


def _make_tweet_result(
    tweet_id: str = "123",
    text: str = "Hello world",
    author: str = "Test User",
    handle: str = "testuser",
    images: list[dict] | None = None,
    quote: dict | None = None,
) -> dict:
    """Build a minimal tweet result node for testing."""
    result: dict = {
        "rest_id": tweet_id,
        "core": {
            "user_results": {
                "result": {
                    "legacy": {
                        "name": author,
                        "screen_name": handle,
                    }
                }
            }
        },
        "legacy": {
            "id_str": tweet_id,
            "full_text": text,
            "extended_entities": {
                "media": images or [],
            },
        },
    }
    if quote:
        result["quoted_status_result"] = {"result": quote}
    return result


def _make_thread_response(*tweet_results: dict) -> dict:
    """Build a TweetDetail GraphQL response with multiple entries."""
    entries = []
    for tr in tweet_results:
        entries.append(
            {
                "content": {
                    "itemContent": {
                        "tweet_results": {"result": tr},
                    }
                }
            }
        )
    return {
        "data": {
            "threaded_conversation_with_injections_v2": {"instructions": [{"entries": entries}]}
        }
    }


def _make_single_response(tweet_result: dict) -> dict:
    """Build a single tweetResult GraphQL response."""
    return {"data": {"tweetResult": {"result": tweet_result}}}


class TestExtractTweetsFromGraphql:
    def test_single_tweet_thread_shape(self) -> None:
        tr = _make_tweet_result(tweet_id="1001", text="First tweet")
        response = _make_thread_response(tr)
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets) == 1
        assert tweets[0].tweet_id == "1001"
        assert tweets[0].text == "First tweet"
        assert tweets[0].order == 0

    def test_thread_with_multiple_tweets(self) -> None:
        t1 = _make_tweet_result(tweet_id="1", text="Part 1", handle="alice")
        t2 = _make_tweet_result(tweet_id="2", text="Part 2", handle="alice")
        t3 = _make_tweet_result(tweet_id="3", text="Part 3", handle="alice")
        response = _make_thread_response(t1, t2, t3)
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets) == 3
        assert [t.order for t in tweets] == [0, 1, 2]
        assert [t.text for t in tweets] == ["Part 1", "Part 2", "Part 3"]

    def test_single_tweet_result_shape(self) -> None:
        tr = _make_tweet_result(tweet_id="2002", text="Standalone tweet")
        response = _make_single_response(tr)
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets) == 1
        assert tweets[0].tweet_id == "2002"

    def test_tweet_with_images(self) -> None:
        images = [
            {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/img1.jpg"},
            {"type": "photo", "media_url_https": "https://pbs.twimg.com/media/img2.jpg"},
            {"type": "video", "media_url_https": "https://pbs.twimg.com/vid1.mp4"},
        ]
        tr = _make_tweet_result(images=images)
        response = _make_thread_response(tr)
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets[0].images) == 2  # only photos
        assert "img1.jpg" in tweets[0].images[0]

    def test_tweet_with_quote_tweet(self) -> None:
        qt = _make_tweet_result(tweet_id="999", text="Original take", handle="bob")
        tr = _make_tweet_result(tweet_id="1000", text="My reply", quote=qt)
        response = _make_thread_response(tr)
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets) == 1
        assert tweets[0].quote_tweet is not None
        assert tweets[0].quote_tweet.tweet_id == "999"
        assert tweets[0].quote_tweet.author_handle == "bob"

    def test_visibility_wrapper(self) -> None:
        inner = _make_tweet_result(tweet_id="555", text="Wrapped tweet")
        wrapped = {"__typename": "TweetWithVisibilityResults", "tweet": inner}
        response = _make_thread_response(wrapped)
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets) == 1
        assert tweets[0].tweet_id == "555"

    def test_conversation_module_items(self) -> None:
        """Test thread replies inside conversation module (items array)."""
        t1 = _make_tweet_result(tweet_id="1", text="Main")
        t2 = _make_tweet_result(tweet_id="2", text="Reply")
        response = {
            "data": {
                "threaded_conversation_with_injections_v2": {
                    "instructions": [
                        {
                            "entries": [
                                {"content": {"itemContent": {"tweet_results": {"result": t1}}}},
                                {
                                    "content": {
                                        "items": [
                                            {
                                                "item": {
                                                    "itemContent": {"tweet_results": {"result": t2}}
                                                }
                                            }
                                        ]
                                    }
                                },
                            ]
                        }
                    ]
                }
            }
        }
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets) == 2
        assert tweets[0].text == "Main"
        assert tweets[1].text == "Reply"

    def test_empty_response(self) -> None:
        assert extract_tweets_from_graphql({}) == []

    def test_malformed_response(self) -> None:
        assert extract_tweets_from_graphql({"data": None}) == []

    def test_missing_legacy(self) -> None:
        """Tweet result without legacy field is skipped."""
        tr = {"rest_id": "999", "core": {}}
        response = _make_thread_response(tr)
        tweets = extract_tweets_from_graphql(response)
        assert len(tweets) == 0


class TestTweetDataSerialization:
    def test_to_dict_simple(self) -> None:
        t = TweetData(tweet_id="1", author="A", author_handle="a", text="hi", order=0)
        d = t.to_dict()
        assert d["tweet_id"] == "1"
        assert "quote_tweet" not in d

    def test_to_dict_with_quote(self) -> None:
        qt = TweetData(tweet_id="2", author="B", author_handle="b", text="original", order=0)
        t = TweetData(
            tweet_id="1",
            author="A",
            author_handle="a",
            text="quote",
            quote_tweet=qt,
            order=0,
        )
        d = t.to_dict()
        assert d["quote_tweet"]["tweet_id"] == "2"


class TestExtractionResult:
    def test_to_dict(self) -> None:
        t = TweetData(tweet_id="1", author="A", author_handle="a", text="hello", order=0)
        r = ExtractionResult(url="https://x.com/a/status/1", tweets=[t])
        d = r.to_dict()
        assert d["url"] == "https://x.com/a/status/1"
        assert len(d["tweets"]) == 1

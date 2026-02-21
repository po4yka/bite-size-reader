"""Tests for Playwright Twitter/X client helpers."""

from __future__ import annotations

from app.adapters.twitter.playwright_client import (
    _merge_captured_tweets,
    _response_matches_requested_tweet,
)


def _make_tweet_result(
    tweet_id: str,
    text: str,
    author: str = "Test User",
    handle: str = "testuser",
) -> dict:
    return {
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
            "extended_entities": {"media": []},
        },
    }


def _make_thread_response(*tweet_results: dict) -> dict:
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


def test_merge_captured_tweets_preserves_global_order_across_responses() -> None:
    r1 = _make_thread_response(
        _make_tweet_result("1", "part 1"),
        _make_tweet_result("2", "part 2"),
    )
    r2 = _make_thread_response(
        _make_tweet_result("3", "part 3"),
        _make_tweet_result("4", "part 4"),
    )

    merged = _merge_captured_tweets([r1, r2])
    assert [t.tweet_id for t in merged] == ["1", "2", "3", "4"]
    assert [t.order for t in merged] == [0, 1, 2, 3]


def test_merge_captured_tweets_deduplicates_by_tweet_id() -> None:
    r1 = _make_thread_response(
        _make_tweet_result("1", "part 1"),
        _make_tweet_result("2", "part 2"),
    )
    r2 = _make_thread_response(
        _make_tweet_result("2", "part 2 duplicate"),
        _make_tweet_result("3", "part 3"),
    )

    merged = _merge_captured_tweets([r1, r2])
    assert [t.tweet_id for t in merged] == ["1", "2", "3"]
    assert [t.order for t in merged] == [0, 1, 2]


def test_response_matches_requested_tweet_with_encoded_variables() -> None:
    response_url = (
        "https://x.com/i/api/graphql/abc/TweetDetail?"
        "variables=%7B%22focalTweetId%22%3A%2212345%22%7D"
    )
    assert _response_matches_requested_tweet(response_url, "12345") is True
    assert _response_matches_requested_tweet(response_url, "99999") is False


def test_response_matches_requested_tweet_without_expectation() -> None:
    assert (
        _response_matches_requested_tweet("https://x.com/i/api/graphql/x/TweetDetail", None) is True
    )

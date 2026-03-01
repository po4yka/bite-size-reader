"""Tests for Playwright Twitter/X client helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adapters.twitter.playwright_client import (
    _load_cookies_netscape,
    _merge_captured_tweets,
    _response_matches_requested_tweet,
    resolve_tco_url,
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


def test_response_matches_requested_tweet_with_raw_query_value() -> None:
    response_url = "https://x.com/i/api/graphql/abc/TweetDetail?focalTweetId=67890"
    assert _response_matches_requested_tweet(response_url, "67890") is True
    assert _response_matches_requested_tweet(response_url, "11111") is False


def test_load_cookies_netscape_keeps_httponly_entries(tmp_path) -> None:
    cookies_file = tmp_path / "cookies.txt"
    cookies_file.write_text(
        "\n".join(
            [
                "# Netscape HTTP Cookie File",
                "#HttpOnly_.x.com\tTRUE\t/\tTRUE\t2147483647\tauth_token\tsecret",
                ".x.com\tTRUE\t/\tTRUE\t2147483647\tct0\tcsrf",
            ]
        )
    )

    cookies = _load_cookies_netscape(cookies_file)

    assert len(cookies) == 2
    assert cookies[0]["name"] == "auth_token"
    assert cookies[0]["httpOnly"] is True
    assert cookies[1]["name"] == "ct0"
    assert cookies[1]["httpOnly"] is False


@pytest.mark.asyncio
async def test_resolve_tco_url_accepts_http_and_mixed_case_scheme(monkeypatch) -> None:
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self) -> _FakeAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def head(self, url: str) -> SimpleNamespace:
            return SimpleNamespace(url="https://resolved.example/final")

    monkeypatch.setattr(
        "app.adapters.twitter.playwright_client.httpx.AsyncClient", _FakeAsyncClient
    )

    assert await resolve_tco_url("http://t.co/abc123") == "https://resolved.example/final"
    assert await resolve_tco_url("HTTPS://t.co/abc123") == "https://resolved.example/final"
    assert await resolve_tco_url("https://example.com/nope") is None

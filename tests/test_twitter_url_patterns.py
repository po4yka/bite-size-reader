"""Tests for Twitter/X URL detection and parsing."""

from __future__ import annotations

import pytest

from app.adapters.twitter.url_patterns import parse_article_url, parse_tweet_url
from app.core.url_utils import (
    compute_dedupe_hash,
    extract_tweet_id,
    is_twitter_article_url,
    is_twitter_url,
)


class TestIsTwitterUrl:
    """Test is_twitter_url() detection."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://x.com/elonmusk/status/1234567890",
            "https://twitter.com/jack/status/9876543210",
            "https://www.x.com/user/status/111",
            "https://mobile.x.com/user/status/222",
            "https://www.twitter.com/user/status/333",
            "https://mobile.twitter.com/user/status/444",
            "http://x.com/user/status/555",
            "https://x.com/user/status/666?s=20",
            "https://x.com/user/status/666/photo/1",
            "https://x.com/i/web/status/777",
            "https://x.com/i/article/1234567890",
            "https://x.com/i/article/1234567890/preview",
            "https://twitter.com/i/article/9876543210",
        ],
    )
    def test_valid_twitter_urls(self, url: str) -> None:
        assert is_twitter_url(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://youtube.com/watch?v=abc",
            "https://example.com/x.com/status/123",
            "https://x.com/user/likes",
            "https://x.com/user",
            "https://my-x.com/user/status/123",
            "https://foo.twitter.com/user/status/123",
            "https://example.com/redirect?target=https://x.com/user/status/123",
            "https://notx.com/user/status/123",
            "",
            None,
        ],
    )
    def test_non_twitter_urls(self, url: str | None) -> None:
        assert is_twitter_url(url) is False


class TestExtractTweetId:
    """Test extract_tweet_id() parsing."""

    def test_x_dot_com(self) -> None:
        assert extract_tweet_id("https://x.com/elonmusk/status/1234567890") == "1234567890"

    def test_twitter_dot_com(self) -> None:
        assert extract_tweet_id("https://twitter.com/jack/status/9876") == "9876"

    def test_with_query_params(self) -> None:
        assert extract_tweet_id("https://x.com/user/status/111?s=20&t=abc") == "111"

    def test_i_web_status(self) -> None:
        assert extract_tweet_id("https://x.com/i/web/status/1234567890") == "1234567890"

    def test_status_with_media_suffix(self) -> None:
        assert extract_tweet_id("https://x.com/user/status/111/photo/1") == "111"

    def test_mobile(self) -> None:
        assert extract_tweet_id("https://mobile.x.com/user/status/222") == "222"

    def test_article_url_returns_none(self) -> None:
        assert extract_tweet_id("https://x.com/i/article/123") is None

    def test_invalid_returns_none(self) -> None:
        assert extract_tweet_id("https://example.com") is None

    def test_none_input(self) -> None:
        assert extract_tweet_id(None) is None

    def test_empty_input(self) -> None:
        assert extract_tweet_id("") is None


class TestIsTwitterArticleUrl:
    """Test is_twitter_article_url() detection."""

    def test_x_article(self) -> None:
        assert is_twitter_article_url("https://x.com/i/article/123456") is True

    def test_twitter_article(self) -> None:
        assert is_twitter_article_url("https://twitter.com/i/article/789") is True

    def test_tweet_is_not_article(self) -> None:
        assert is_twitter_article_url("https://x.com/user/status/123") is False

    def test_non_twitter(self) -> None:
        assert is_twitter_article_url("https://example.com") is False


class TestParseTweetUrl:
    """Test parse_tweet_url() detailed parsing."""

    def test_basic(self) -> None:
        user, tweet_id = parse_tweet_url("https://x.com/elonmusk/status/1234567890")
        assert user == "elonmusk"
        assert tweet_id == "1234567890"

    def test_twitter_domain(self) -> None:
        user, tweet_id = parse_tweet_url("https://twitter.com/jack/status/999")
        assert user == "jack"
        assert tweet_id == "999"

    def test_with_trailing_slash(self) -> None:
        user, tweet_id = parse_tweet_url("https://x.com/user/status/111/")
        assert user == "user"
        assert tweet_id == "111"

    def test_with_query_params(self) -> None:
        user, tweet_id = parse_tweet_url("https://x.com/user/status/222?s=20")
        assert user == "user"
        assert tweet_id == "222"

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Not a valid tweet URL"):
            parse_tweet_url("https://example.com/not-a-tweet")


class TestParseArticleUrl:
    """Test parse_article_url() parsing."""

    def test_basic(self) -> None:
        assert parse_article_url("https://x.com/i/article/123456") == "123456"

    def test_non_article(self) -> None:
        assert parse_article_url("https://x.com/user/status/123") is None

    def test_with_trailing_slash(self) -> None:
        assert parse_article_url("https://x.com/i/article/789/") == "789"

    def test_with_safe_suffix(self) -> None:
        assert parse_article_url("https://x.com/i/article/789/preview") == "789"


class TestTwitterDedupeCanonicalization:
    def test_share_params_do_not_change_dedupe_hash(self) -> None:
        h1 = compute_dedupe_hash("https://x.com/user/status/123?s=20&t=AAA")
        h2 = compute_dedupe_hash("https://x.com/user/status/123?s=20&t=BBB")
        h3 = compute_dedupe_hash("https://x.com/i/web/status/123?utm_source=twitter")
        assert h1 == h2 == h3

"""Tests for Substack URL resolution utilities."""

from app.adapters.rss.substack import is_substack_url, resolve_substack_feed_url


class TestIsSubstackUrl:
    def test_standard_substack_url(self) -> None:
        assert is_substack_url("https://platformer.substack.com") is True

    def test_substack_article_url(self) -> None:
        assert is_substack_url("https://platformer.substack.com/p/some-article") is True

    def test_substack_feed_url(self) -> None:
        assert is_substack_url("https://platformer.substack.com/feed") is True

    def test_bare_substack_domain(self) -> None:
        assert is_substack_url("platformer.substack.com") is True

    def test_non_substack_url(self) -> None:
        assert is_substack_url("https://example.com") is False

    def test_custom_domain(self) -> None:
        assert is_substack_url("https://www.platformer.news") is False

    def test_empty_string(self) -> None:
        assert is_substack_url("") is False


class TestResolveSubstackFeedUrl:
    def test_bare_name(self) -> None:
        assert resolve_substack_feed_url("platformer") == "https://platformer.substack.com/feed"

    def test_bare_name_with_spaces(self) -> None:
        assert resolve_substack_feed_url("  platformer  ") == "https://platformer.substack.com/feed"

    def test_full_substack_url(self) -> None:
        result = resolve_substack_feed_url("https://platformer.substack.com")
        assert result == "https://platformer.substack.com/feed"

    def test_substack_url_with_path(self) -> None:
        result = resolve_substack_feed_url("https://platformer.substack.com/p/some-article")
        assert result == "https://platformer.substack.com/feed"

    def test_substack_url_already_feed(self) -> None:
        result = resolve_substack_feed_url("https://platformer.substack.com/feed")
        assert result == "https://platformer.substack.com/feed"

    def test_without_scheme(self) -> None:
        result = resolve_substack_feed_url("platformer.substack.com")
        assert result == "https://platformer.substack.com/feed"

    def test_custom_domain(self) -> None:
        result = resolve_substack_feed_url("https://www.platformer.news")
        assert result == "https://www.platformer.news/feed"

    def test_custom_domain_already_feed(self) -> None:
        result = resolve_substack_feed_url("https://www.platformer.news/feed")
        assert result == "https://www.platformer.news/feed"

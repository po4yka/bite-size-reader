"""Tests for Twitter/X text formatting for LLM summarization."""

from __future__ import annotations

from app.adapters.twitter.graphql_parser import TweetData
from app.adapters.twitter.text_formatter import (
    format_article_for_summary,
    format_tweets_for_summary,
    parse_article_header,
)


def _tweet(
    text: str = "Hello",
    handle: str = "user",
    author: str = "User",
    tweet_id: str = "1",
    order: int = 0,
    quote: TweetData | None = None,
) -> TweetData:
    return TweetData(
        tweet_id=tweet_id,
        author=author,
        author_handle=handle,
        text=text,
        order=order,
        quote_tweet=quote,
    )


class TestFormatTweetsForSummary:
    def test_single_tweet(self) -> None:
        tweets = [_tweet(text="Important announcement", handle="ceo", author="CEO")]
        result = format_tweets_for_summary(tweets)
        assert "@ceo (CEO):" in result
        assert "Important announcement" in result

    def test_single_tweet_keeps_tco(self) -> None:
        tweets = [_tweet(text="Check this out https://t.co/abc123 for details")]
        result = format_tweets_for_summary(tweets)
        assert "https://t.co/abc123" in result
        assert "Check this out" in result
        assert "for details" in result

    def test_thread(self) -> None:
        tweets = [
            _tweet(text="Part one", handle="alice", author="Alice", order=0),
            _tweet(text="Part two", handle="alice", author="Alice", order=1),
            _tweet(text="Part three", handle="alice", author="Alice", order=2),
        ]
        result = format_tweets_for_summary(tweets)
        assert "Thread by @alice" in result
        assert "[1/3] Part one" in result
        assert "[2/3] Part two" in result
        assert "[3/3] Part three" in result

    def test_thread_with_quote(self) -> None:
        qt = _tweet(text="Original insight", handle="bob", author="Bob")
        tweets = [
            _tweet(text="Adding context", handle="alice", author="Alice", quote=qt),
            _tweet(text="More thoughts", handle="alice", author="Alice", order=1),
        ]
        result = format_tweets_for_summary(tweets)
        assert "Quoting @bob" in result
        assert "Original insight" in result

    def test_single_tweet_with_quote(self) -> None:
        qt = _tweet(text="Hot take", handle="bob", author="Bob")
        tweets = [_tweet(text="Disagree", handle="alice", author="Alice", quote=qt)]
        result = format_tweets_for_summary(tweets)
        assert "@alice (Alice):" in result
        assert "Disagree" in result
        assert "Quoting @bob (Bob):" in result
        assert "Hot take" in result

    def test_empty_list(self) -> None:
        assert format_tweets_for_summary([]) == ""


class TestFormatArticleForSummary:
    def test_full_article(self) -> None:
        data = {
            "title": "My Great Article",
            "author": "Jane Doe",
            "content": "This is the article body.\n\nWith multiple paragraphs.",
        }
        result = format_article_for_summary(data)
        assert "# My Great Article" in result
        assert "By Jane Doe" in result
        assert "This is the article body." in result

    def test_content_only(self) -> None:
        data = {"content": "Just the content"}
        result = format_article_for_summary(data)
        assert result == "Just the content"

    def test_excessive_newlines_collapsed(self) -> None:
        data = {"content": "Para 1\n\n\n\n\nPara 2"}
        result = format_article_for_summary(data)
        assert "\n\n\n" not in result
        assert "Para 1\n\nPara 2" in result

    def test_empty_article(self) -> None:
        result = format_article_for_summary({})
        assert result == ""

    def test_bad_title_x_parsed_from_content(self) -> None:
        """When DOM returns title='X', parse real title from content."""
        data = {
            "title": "X",
            "author": "",
            "content": (
                "My Real Title\nJohn Smith\n@johnsmith\n\u00b7\nFeb 8\nFollow\nThis is the body."
            ),
        }
        result = format_article_for_summary(data)
        assert "# My Real Title" in result
        assert "By John Smith" in result
        assert "This is the body." in result
        assert "# X" not in result


class TestParseArticleHeader:
    """Parse title/author/handle from article content text."""

    def test_pattern_a_standard(self) -> None:
        content = (
            "My Great Article Title\n"
            "John Smith\n"
            "@johnsmith\n"
            "\u00b7\n"
            "Feb 8\n"
            "Follow\n"
            "This is the body of the article."
        )
        title, author, handle, body = parse_article_header(content)
        assert title == "My Great Article Title"
        assert author == "John Smith"
        assert handle == "johnsmith"
        assert body == "This is the body of the article."

    def test_pattern_a_with_subscribe(self) -> None:
        content = (
            "Advanced AI Systems\n"
            "Jane Doe\n"
            "@janedoe\n"
            "\u00b7\n"
            "Jan 27\n"
            "Subscribe\n"
            "4\n"
            "11\n"
            "119\n"
            "19K\n"
            "Body starts here."
        )
        title, author, handle, body = parse_article_header(content)
        assert title == "Advanced AI Systems"
        assert author == "Jane Doe"
        assert handle == "janedoe"
        assert body == "Body starts here."

    def test_pattern_a_no_follow(self) -> None:
        content = "Simple Title\nBob\n@bob123\n\u00b7\n3h\nThe article content."
        title, author, handle, body = parse_article_header(content)
        assert title == "Simple Title"
        assert author == "Bob"
        assert handle == "bob123"
        assert body == "The article content."

    def test_pattern_a_full_date(self) -> None:
        content = (
            "Year End Review\nAuthor Name\n@author\n\u00b7\nDec 16, 2025\nFollow\nContent here."
        )
        title, author, _handle, body = parse_article_header(content)
        assert title == "Year End Review"
        assert author == "Author Name"
        assert body == "Content here."

    def test_pattern_b_author_first(self) -> None:
        content = (
            "Alice Wonder\n@alicew\n\u00b7\nFeb 20\nArticle\nThe Real Title\nAnd this is the body."
        )
        title, author, handle, body = parse_article_header(content)
        assert title == "The Real Title"
        assert author == "Alice Wonder"
        assert handle == "alicew"
        assert body == "And this is the body."

    def test_pattern_b_without_article_label(self) -> None:
        content = (
            "Charlie Brown\n"
            "@charlie\n"
            "\u00b7\n"
            "5m\n"
            "Follow\n"
            "Peanuts Philosophy\n"
            "Good grief, here's the body."
        )
        title, author, handle, body = parse_article_header(content)
        assert title == "Peanuts Philosophy"
        assert author == "Charlie Brown"
        assert handle == "charlie"
        assert body == "Good grief, here's the body."

    def test_empty_content(self) -> None:
        title, author, handle, _body = parse_article_header("")
        assert title == ""
        assert author == ""
        assert handle == ""

    def test_single_line(self) -> None:
        title, author, handle, _body = parse_article_header("Just a title")
        assert title == "Just a title"
        assert author == ""
        assert handle == ""

from __future__ import annotations

import pytest

from app.core.channel_utils import parse_channel_input


class TestParseChannelInputSuccess:
    """Valid inputs that should return (username, None)."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # Plain valid usernames
            ("technews", "technews"),
            ("some_channel", "some_channel"),
            ("a1234", "a1234"),
            # Exactly 5 chars (minimum)
            ("abcde", "abcde"),
            # Exactly 32 chars (maximum)
            ("a" + "b" * 31, "a" + "b" * 31),
            # @ prefix stripped and lowercased
            ("@TechNews", "technews"),
            # Case normalization
            ("TechNEWS", "technews"),
            # t.me link (no scheme)
            ("t.me/some_channel", "some_channel"),
            # https://t.me link with case
            ("https://t.me/TechNews", "technews"),
            # http://t.me link
            ("http://t.me/TechNews", "technews"),
            # telegram.me link
            ("https://telegram.me/chan_name", "chan_name"),
            # Trailing slash
            ("t.me/channel/", "channel"),
            # Whitespace stripping
            ("  @technews  ", "technews"),
        ],
        ids=[
            "plain-technews",
            "plain-underscore",
            "plain-a1234",
            "min-length-5",
            "max-length-32",
            "at-prefix",
            "case-normalize",
            "t.me-no-scheme",
            "https-t.me",
            "http-t.me",
            "telegram.me",
            "trailing-slash",
            "whitespace-strip",
        ],
    )
    def test_valid_input(self, raw: str, expected: str) -> None:
        username, error = parse_channel_input(raw)
        assert username == expected
        assert error is None


class TestParseChannelInputFailure:
    """Invalid inputs that should return (None, error_message)."""

    @pytest.mark.parametrize(
        "raw",
        [
            # Empty / whitespace
            "",
            "   ",
            # Too short (< 5 after normalization)
            "abc",
            # Starts with digit
            "1channel",
            # Starts with underscore
            "_channel",
            # Contains invalid characters (hyphen)
            "chan-name",
            # Too long (33 chars)
            "a" + "b" * 32,
        ],
        ids=[
            "empty",
            "whitespace-only",
            "too-short",
            "starts-with-digit",
            "starts-with-underscore",
            "invalid-chars-hyphen",
            "too-long-33",
        ],
    )
    def test_invalid_input(self, raw: str) -> None:
        username, error = parse_channel_input(raw)
        assert username is None
        assert error is not None

    def test_empty_returns_specific_message(self) -> None:
        _, error = parse_channel_input("")
        assert error == "Please provide a channel name."

    def test_whitespace_returns_specific_message(self) -> None:
        _, error = parse_channel_input("   ")
        assert error == "Please provide a channel name."

    def test_invalid_username_error_includes_name(self) -> None:
        _, error = parse_channel_input("1channel")
        assert error is not None
        assert "1channel" in error

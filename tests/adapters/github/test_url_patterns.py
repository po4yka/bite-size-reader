"""Tests for GitHub URL detection and parsing utilities."""

import pytest

from app.adapters.github.url_patterns import is_github_repo_url, parse_github_repo_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/tiangolo/fastapi", True),
        ("https://github.com/tiangolo/fastapi/", True),
        ("https://github.com/tiangolo/fastapi.git", True),
        ("https://www.github.com/tiangolo/fastapi", True),
        ("http://github.com/tiangolo/fastapi", True),
        ("https://github.com/tiangolo/fastapi/issues", False),
        ("https://github.com/tiangolo/fastapi/issues/1", False),
        ("https://github.com/tiangolo/fastapi/pull/123", False),
        ("https://github.com/tiangolo/fastapi/blob/main/README.md", False),
        ("https://github.com/tiangolo/fastapi/wiki", False),
        ("https://github.com/tiangolo/fastapi/actions", False),
        ("https://github.com/tiangolo/fastapi/releases", False),
        ("https://github.com/tiangolo/fastapi/tags", False),
        ("https://github.com/tiangolo/fastapi/network", False),
        ("https://github.com/tiangolo/fastapi/settings", False),
        ("https://github.com/tiangolo/fastapi/discussions", False),
        ("https://github.com/tiangolo/fastapi/security", False),
        ("https://github.com/tiangolo/fastapi/projects", False),
        ("https://github.com/tiangolo/fastapi/tree/main/docs", False),
        ("https://github.com/tiangolo/fastapi/commits/main", False),
        ("https://gist.github.com/abc123", False),
        ("https://raw.githubusercontent.com/owner/repo/main/file", False),
        ("https://api.github.com/repos/tiangolo/fastapi", False),
        ("https://example.com/tiangolo/fastapi", False),
        ("https://github.com/tiangolo", False),  # just owner, no repo
        ("https://github.com/", False),
        ("not a url at all", False),
        ("", False),
    ],
)
def test_is_github_repo_url(url: str, expected: bool) -> None:
    assert is_github_repo_url(url) is expected


def test_parse_github_repo_url_happy() -> None:
    assert parse_github_repo_url("https://github.com/tiangolo/fastapi") == (
        "tiangolo",
        "fastapi",
    )


def test_parse_github_repo_url_strips_git_suffix() -> None:
    assert parse_github_repo_url("https://github.com/tiangolo/fastapi.git") == (
        "tiangolo",
        "fastapi",
    )


def test_parse_github_repo_url_with_trailing_slash() -> None:
    assert parse_github_repo_url("https://github.com/tiangolo/fastapi/") == (
        "tiangolo",
        "fastapi",
    )


def test_parse_github_repo_url_invalid_returns_none() -> None:
    assert parse_github_repo_url("https://github.com/tiangolo/fastapi/issues") is None


def test_parse_github_repo_url_handles_dots_in_repo_name() -> None:
    assert parse_github_repo_url("https://github.com/sindresorhus/awesome.js") == (
        "sindresorhus",
        "awesome.js",
    )


def test_parse_github_repo_url_handles_dashes() -> None:
    assert parse_github_repo_url("https://github.com/great-scott/back-to-the-future") == (
        "great-scott",
        "back-to-the-future",
    )

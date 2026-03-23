from __future__ import annotations

import socket

from app.core.urls.twitter import canonicalize_twitter_url, extract_twitter_status_parts


def test_extract_twitter_status_parts_handles_mobile_hosts() -> None:
    parts = extract_twitter_status_parts("https://mobile.x.com/user/status/123/photo/1")

    assert parts == ("user", "123")


def test_canonicalize_twitter_url_is_network_independent(
    monkeypatch,
) -> None:
    def fail_getaddrinfo(*_args, **_kwargs):
        msg = "twitter canonicalization should not resolve DNS"
        raise AssertionError(msg)

    monkeypatch.setattr(socket, "getaddrinfo", fail_getaddrinfo)

    assert canonicalize_twitter_url("https://twitter.com/user/status/123?s=20") == (
        "https://x.com/i/web/status/123"
    )
    assert canonicalize_twitter_url("https://twitter.com/i/article/456/preview") == (
        "https://x.com/i/article/456"
    )

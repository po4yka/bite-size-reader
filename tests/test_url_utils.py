from __future__ import annotations

from app.core import url_utils


def test_url_utils_facade_exposes_generic_helpers() -> None:
    assert url_utils.normalize_url("HTTPS://Example.COM/Path/?b=2&utm_source=x&a=1#frag") == (
        "https://example.com/Path?a=1&b=2"
    )
    assert len(url_utils.url_hash_sha256("https://example.com/path?a=1")) == 64
    assert url_utils.looks_like_url("see https://example.org/ok?x=1") is True
    assert url_utils.extract_all_urls("www.example.com/path") == ["https://www.example.com/path"]


def test_url_utils_facade_exposes_platform_helpers() -> None:
    assert url_utils.canonicalize_twitter_url("https://twitter.com/user/status/123?s=20") == (
        "https://x.com/i/web/status/123"
    )
    assert url_utils.is_twitter_url("https://x.com/user/status/123") is True
    assert url_utils.extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert url_utils.is_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ") is True

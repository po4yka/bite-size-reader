from __future__ import annotations

from app.core.urls.extraction import extract_all_urls, looks_like_url


def test_looks_like_url_detects_protocol_and_www_variants() -> None:
    assert looks_like_url("see https://example.org/ok?x=1")
    assert looks_like_url("www.example.com/path")
    assert not looks_like_url("no url here")


def test_extract_all_urls_prioritizes_protocol_matches_then_www_variants() -> None:
    urls = extract_all_urls("Visit www.foo.org and https://bar.com and www.foo.org")

    assert urls == ["https://bar.com", "https://www.foo.org"]


def test_extraction_guards_on_oversized_input() -> None:
    text = "x" * (51 * 1024)

    assert looks_like_url(text) is False
    assert extract_all_urls(text) == []

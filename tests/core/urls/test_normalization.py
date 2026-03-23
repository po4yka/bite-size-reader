from __future__ import annotations

import pytest

from app.core.urls import normalization


def test_normalize_url_normalizes_components(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(normalization, "validate_url_input", lambda _url: None)

    normalized = normalization.normalize_url("HTTPS://Example.COM/Path/?b=2&utm_source=x&a=1#frag")

    assert normalized == "https://example.com/Path?a=1&b=2"


def test_normalize_url_reencodes_paths_and_preserves_blank_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(normalization, "validate_url_input", lambda _url: None)

    normalized = normalization.normalize_url(
        "https://Example.COM/hello world/?b=&utm_campaign=x&a=1"
    )

    assert normalized == "https://example.com/hello%20world?a=1&b="


def test_normalize_url_handles_missing_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(normalization, "validate_url_input", lambda _url: None)

    normalized = normalization.normalize_url("Example.com/Path?B=2&A=1")

    assert normalized == "http://example.com/Path?A=1&B=2"


def test_normalize_url_rejects_credential_injection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(normalization, "validate_url_input", lambda _url: None)

    with pytest.raises(ValueError, match="hostname contains suspicious characters"):
        normalization.normalize_url("https://user:pass@example.com/path")


def test_compute_dedupe_hash_canonicalizes_twitter_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(normalization, "validate_url_input", lambda _url: None)

    first = normalization.compute_dedupe_hash("https://x.com/user/status/123?s=20&t=AAA")
    second = normalization.compute_dedupe_hash("https://x.com/i/web/status/123?utm_source=twitter")

    assert first == second

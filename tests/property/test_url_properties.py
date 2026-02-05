"""Property-based tests for URL handling.

Uses Hypothesis to generate diverse URL inputs and verify:
- Normalization idempotence
- Hash determinism
- No exceptions on valid input patterns
"""

from __future__ import annotations

import pytest

# Try to import hypothesis, skip tests if not available
hypothesis = pytest.importorskip("hypothesis")
from hypothesis import assume, given, settings, strategies as st


class TestURLNormalizationProperties:
    """Property-based tests for URL normalization."""

    @given(
        scheme=st.sampled_from(["http", "https"]),
        host=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789.-",
            min_size=1,
            max_size=50,
        ).filter(lambda x: x[0].isalnum() and x[-1].isalnum() if x else False),
        path=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789/-_.",
            min_size=0,
            max_size=100,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_normalize_url_never_crashes(self, scheme: str, host: str, path: str) -> None:
        """Verify normalize_url never raises exceptions on valid URL components."""
        from app.core.url_utils import normalize_url

        url = f"{scheme}://{host}{path}"
        try:
            result = normalize_url(url)
            # Result should be a string
            assert isinstance(result, str)
        except ValueError:
            # ValueError is acceptable for invalid URLs
            pass

    @given(
        base_url=st.sampled_from(
            [
                "https://example.com/article",
                "https://medium.com/@user/post",
                "https://github.com/user/repo",
            ]
        ),
        params=st.dictionaries(
            keys=st.text(alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=10),
            values=st.text(min_size=0, max_size=20),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_normalize_url_idempotent(self, base_url: str, params: dict) -> None:
        """Verify normalizing twice produces the same result."""
        from urllib.parse import urlencode

        from app.core.url_utils import normalize_url

        # Build URL with params
        url = f"{base_url}?{urlencode(params)}" if params else base_url

        try:
            first_norm = normalize_url(url)
            second_norm = normalize_url(first_norm)
            assert first_norm == second_norm, "Normalization is not idempotent"
        except ValueError:
            pass  # Invalid URL is acceptable

    @given(
        url=st.sampled_from(
            [
                "https://example.com/page",
                "https://example.com/page?a=1",
                "https://example.com/page?a=1&b=2",
            ]
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_hash_url_deterministic(self, url: str) -> None:
        """Verify URL hashing is deterministic."""
        from app.core.url_utils import url_hash_sha256

        hash1 = url_hash_sha256(url)
        hash2 = url_hash_sha256(url)
        hash3 = url_hash_sha256(url)

        assert hash1 == hash2 == hash3, "URL hash is not deterministic"
        assert len(hash1) == 64, "SHA256 hash should be 64 hex characters"

    @given(url=st.from_regex(r"https?://[a-z0-9.-]+/[a-z0-9/_-]*", fullmatch=True))
    @settings(max_examples=100, deadline=None)
    def test_normalized_url_preserves_essential_parts(self, url: str) -> None:
        """Verify essential URL parts are preserved after normalization."""
        from urllib.parse import urlparse

        from app.core.url_utils import normalize_url

        try:
            normalized = normalize_url(url)
            original = urlparse(url)
            result = urlparse(normalized)

            # Scheme should match (http may upgrade to https)
            assert result.scheme in ("http", "https")

            # Host should be present
            assert result.netloc, "Host was lost during normalization"

        except ValueError:
            pass  # Invalid URL is acceptable


class TestYouTubeURLProperties:
    """Property-based tests for YouTube URL handling."""

    @given(
        video_id=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-",
            min_size=11,
            max_size=11,
        ),
        format_type=st.sampled_from(
            [
                "watch",
                "embed",
                "v",
                "shorts",
            ]
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_youtube_url_detection(self, video_id: str, format_type: str) -> None:
        """Verify YouTube URLs are correctly detected regardless of format."""
        from app.core.url_utils import is_youtube_url

        # Build various YouTube URL formats
        urls = [
            f"https://youtube.com/watch?v={video_id}",
            f"https://www.youtube.com/watch?v={video_id}",
            f"https://youtu.be/{video_id}",
            f"https://m.youtube.com/watch?v={video_id}",
        ]

        for url in urls:
            result = is_youtube_url(url)
            assert result is True, f"Failed to detect YouTube URL: {url}"

    @given(
        domain=st.sampled_from(
            [
                "example.com",
                "vimeo.com",
                "dailymotion.com",
                "notube.com",
                "youtube-fake.com",
            ]
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_non_youtube_urls_rejected(self, domain: str) -> None:
        """Verify non-YouTube URLs are not detected as YouTube."""
        from app.core.url_utils import is_youtube_url

        url = f"https://{domain}/watch?v=dQw4w9WgXcQ"
        result = is_youtube_url(url)
        assert result is False, f"Incorrectly detected as YouTube: {url}"


class TestURLHashProperties:
    """Property-based tests for URL hashing."""

    @given(
        url1=st.text(min_size=1, max_size=200),
        url2=st.text(min_size=1, max_size=200),
    )
    @settings(max_examples=100, deadline=None)
    def test_different_urls_different_hashes(self, url1: str, url2: str) -> None:
        """Verify different URLs produce different hashes (collision resistance)."""
        assume(url1 != url2)
        assume(url1.strip())  # skip whitespace-only strings (invalid input)
        assume(url2.strip())

        from app.core.url_utils import url_hash_sha256

        hash1 = url_hash_sha256(url1)
        hash2 = url_hash_sha256(url2)

        # Hashes should be different (with overwhelming probability)
        # Note: This could theoretically fail due to hash collision,
        # but the probability is ~1/2^256, effectively zero
        assert hash1 != hash2, "Hash collision detected (extremely unlikely)"

    @given(
        url=st.text(min_size=1, max_size=500),
    )
    @settings(max_examples=100, deadline=None)
    def test_hash_format(self, url: str) -> None:
        """Verify hash output format is consistent."""
        assume(url.strip())  # skip whitespace-only strings (invalid input)

        from app.core.url_utils import url_hash_sha256

        result = url_hash_sha256(url)

        # SHA256 produces 64 hex characters
        assert len(result) == 64, f"Hash length should be 64, got {len(result)}"
        assert all(c in "0123456789abcdef" for c in result), "Hash contains non-hex chars"

"""Hashing helpers for URL deduplication used during sync."""

from __future__ import annotations

from app.adapters.karakeep.sync.constants import LEGACY_HASH_LENGTH
from app.core.url_utils import normalize_url, url_hash_sha256


def _url_hash(url: str) -> str:
    """Generate consistent hash for URL deduplication.

    Uses full 64-char SHA256 for consistency with the rest of the codebase.
    """
    normalized = normalize_url(url) or url
    return url_hash_sha256(normalized)


def _check_hash_in_set(url_hash: str, hash_set: set[str]) -> bool:
    """Check if URL hash matches any hash in the set (handles legacy hashes)."""
    if url_hash in hash_set:
        return True
    legacy_hash = url_hash[:LEGACY_HASH_LENGTH]
    return legacy_hash in hash_set

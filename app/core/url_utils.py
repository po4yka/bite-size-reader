"""Compatibility facade for focused URL utility modules."""

from __future__ import annotations

from app.core.urls.extraction import extract_all_urls, looks_like_url
from app.core.urls.normalization import (
    TRACKING_PARAMS,
    compute_dedupe_hash,
    extract_domain,
    normalize_url,
    url_hash_sha256,
)
from app.core.urls.twitter import (
    canonicalize_twitter_url,
    extract_tweet_id,
    extract_twitter_article_id,
    extract_twitter_status_id,
    extract_twitter_status_parts,
    is_twitter_article_url,
    is_twitter_url,
)
from app.core.urls.validation import dns_cache_scope, validate_url_input
from app.core.urls.youtube import extract_youtube_video_id, is_youtube_url

__all__ = [
    "TRACKING_PARAMS",
    "canonicalize_twitter_url",
    "compute_dedupe_hash",
    "dns_cache_scope",
    "extract_all_urls",
    "extract_domain",
    "extract_tweet_id",
    "extract_twitter_article_id",
    "extract_twitter_status_id",
    "extract_twitter_status_parts",
    "extract_youtube_video_id",
    "is_twitter_article_url",
    "is_twitter_url",
    "is_youtube_url",
    "looks_like_url",
    "normalize_url",
    "url_hash_sha256",
    "validate_url_input",
]

"""Backward-compat re-export — real implementation in app/infrastructure/cache/trending_cache."""

from app.infrastructure.cache.trending_cache import (  # noqa: F401
    clear_trending_cache,
    get_trending_payload,
)

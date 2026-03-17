"""Backward-compat re-export — real implementation in app/application/services/adaptive_timeout."""

from app.application.services.adaptive_timeout import (  # noqa: F401
    AdaptiveTimeoutService,
    CacheEntry,
    TimeoutCache,
    TimeoutEstimate,
)

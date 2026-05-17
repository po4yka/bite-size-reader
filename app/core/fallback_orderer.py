"""Latency-aware fallback model ordering.

Re-orders the fallback model chain (preserving the user-configured
primary) to minimise expected wall-clock to first-success based on
recently observed P95 latency per model.

Behaviour:
  * Primary stays at index 0 (user-configured first choice).
  * Models with sufficient observed samples are sorted by P95 ascending.
  * Cold-start models (no samples or fewer than the sufficiency
    threshold) are appended after observed models.
  * A stickiness factor prevents thrashing when latencies are similar:
    a model only moves ahead of the next one when its P95 is at least
    ``stickiness_factor`` times smaller.
  * Per-request results are cached in-process for ``ttl_seconds`` to
    avoid hammering the latency-stats repository on the hot path.
  * Any repository exception falls through to the configured order.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

from app.core.logging_utils import get_logger

if TYPE_CHECKING:
    from app.infrastructure.persistence.repositories.latency_stats_repository import (
        LatencyStats,
    )

logger = get_logger(__name__)


class _LatencyRepo(Protocol):
    async def async_get_model_latency_stats(self, model: str, days: int = 7) -> LatencyStats: ...


class FallbackOrderer:
    def __init__(
        self,
        *,
        repo: _LatencyRepo | None,
        stickiness_factor: float = 2.0,
        ttl_seconds: float = 300.0,
        observation_days: int = 7,
    ) -> None:
        self._repo = repo
        self._stickiness = stickiness_factor
        self._ttl = ttl_seconds
        self._observation_days = observation_days
        self._cache: dict[str, tuple[float, LatencyStats]] = {}

    async def order(self, *, primary: str, fallbacks: tuple[str, ...]) -> list[str]:
        # Always strip primary from the candidate set; preserve original
        # configured order amongst the rest.
        candidates = [m for m in fallbacks if m != primary]
        if self._repo is None or not candidates:
            return [primary, *candidates]

        try:
            observed: list[tuple[str, float]] = []
            cold: list[str] = []
            for model in candidates:
                stats = await self._lookup(model)
                if stats.has_sufficient_data and stats.p95_ms is not None:
                    observed.append((model, stats.p95_ms))
                else:
                    cold.append(model)
        except Exception as exc:
            logger.warning(
                "fallback_orderer_repo_error",
                extra={"error": str(exc)},
            )
            return [primary, *candidates]

        ranked_observed = _rank_with_stickiness(
            observed, configured=candidates, stickiness=self._stickiness
        )
        return [primary, *ranked_observed, *cold]

    async def _lookup(self, model: str) -> LatencyStats:
        now = time.monotonic()
        cached = self._cache.get(model)
        if cached is not None:
            stamp, stats = cached
            if self._ttl > 0 and (now - stamp) < self._ttl:
                return stats
        assert self._repo is not None  # narrowed in order()
        stats = await self._repo.async_get_model_latency_stats(model, days=self._observation_days)
        self._cache[model] = (now, stats)
        return stats


def _rank_with_stickiness(
    observed: list[tuple[str, float]],
    *,
    configured: list[str],
    stickiness: float,
) -> list[str]:
    """Return models ordered by latency with stickiness bias.

    Models within ``stickiness`` factor of each other keep their
    configured-order position; only meaningful gaps (faster_p95 *
    stickiness <= slower_p95) override the configured order.
    """
    if not observed:
        return []
    # Sort observed candidates by configured order first so ties resolve
    # deterministically.
    position = {m: i for i, m in enumerate(configured)}
    by_position = sorted(observed, key=lambda mp: position[mp[0]])
    # Greedy: walk by_position; for each, see if a later (in configured
    # order) candidate is significantly faster, and promote it.
    result: list[tuple[str, float]] = []
    remaining = by_position.copy()
    while remaining:
        head_model, head_p95 = remaining[0]
        promoted_idx = 0
        for idx in range(1, len(remaining)):
            cand_model, cand_p95 = remaining[idx]
            if cand_p95 > 0 and head_p95 >= cand_p95 * stickiness:
                head_model, head_p95 = cand_model, cand_p95
                promoted_idx = idx
        result.append((head_model, head_p95))
        remaining.pop(promoted_idx)
    return [m for m, _ in result]


__all__: list[str] = ["FallbackOrderer"]

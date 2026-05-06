"""SQLAlchemy repository for latency statistics.

This repository queries CrawlResult and LLMCall tables to compute
P50/P95 latency statistics for adaptive timeout estimation.
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.core.call_status import CallStatus
from app.core.time_utils import UTC
from app.core.url_utils import extract_domain
from app.db.models import CrawlResult, LLMCall, Request
from app.domain.models.request import RequestStatus

if TYPE_CHECKING:
    from app.db.session import Database


@dataclass(frozen=True)
class LatencyStats:
    """Latency statistics for a domain, model, or global scope."""

    p50_ms: float | None
    p95_ms: float | None
    sample_count: int
    oldest_sample_ts: _dt.datetime | None = None
    newest_sample_ts: _dt.datetime | None = None

    @property
    def has_sufficient_data(self) -> bool:
        """Check if we have enough samples for confident estimation."""
        return self.sample_count >= 10 and self.p95_ms is not None


def _compute_percentile(values: list[int], percentile: float) -> float | None:
    """Compute percentile from a sorted list of values.

    Uses linear interpolation between closest ranks (same as numpy's 'linear' method).
    """
    if not values:
        return None

    n = len(values)
    if n == 1:
        return float(values[0])

    # Sort the values
    sorted_values = sorted(values)

    # Compute the rank (0-indexed)
    rank = percentile * (n - 1)
    lower_idx = math.floor(rank)
    upper_idx = math.ceil(rank)

    if lower_idx == upper_idx:
        return float(sorted_values[lower_idx])

    # Linear interpolation
    fraction = rank - lower_idx
    return sorted_values[lower_idx] + fraction * (
        sorted_values[upper_idx] - sorted_values[lower_idx]
    )


_extract_domain = extract_domain


class SqliteLatencyStatsRepositoryAdapter:
    """Repository for querying latency statistics from crawl results and LLM calls."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def async_get_domain_latency_stats(self, domain: str, days: int = 7) -> LatencyStats:
        """Get latency statistics for a specific domain.

        Queries CrawlResult table for successful crawls from the given domain
        within the specified time window.

        Args:
            domain: The domain to query (e.g., "example.com")
            days: Number of days of history to consider

        Returns:
            LatencyStats with P50/P95 and sample count
        """

        cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)
        async with self._database.session() as session:
            rows = await session.execute(
                select(CrawlResult.latency_ms, CrawlResult.updated_at, Request.normalized_url)
                .join(Request, CrawlResult.request_id == Request.id)
                .where(
                    CrawlResult.latency_ms.is_not(None),
                    CrawlResult.firecrawl_success.is_(True),
                    CrawlResult.updated_at >= cutoff,
                )
            )
            latencies: list[int] = []
            timestamps: list[_dt.datetime] = []
            expected_domain = domain.lower()

            for latency_ms, updated_at, normalized_url in rows:
                if _extract_domain(normalized_url) != expected_domain:
                    continue
                latencies.append(int(latency_ms))
                if updated_at:
                    timestamps.append(updated_at)

        return _stats_from_samples(latencies, timestamps)

    async def async_get_model_latency_stats(self, model: str, days: int = 7) -> LatencyStats:
        """Get latency statistics for a specific LLM model.

        Queries LLMCall table for successful calls using the given model
        within the specified time window.

        Args:
            model: The model identifier (e.g., "deepseek/deepseek-v3.2")
            days: Number of days of history to consider

        Returns:
            LatencyStats with P50/P95 and sample count
        """

        cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)
        async with self._database.session() as session:
            rows = await session.execute(
                select(LLMCall.latency_ms, LLMCall.created_at).where(
                    LLMCall.model == model,
                    LLMCall.latency_ms.is_not(None),
                    LLMCall.status == CallStatus.OK.value,
                    LLMCall.created_at >= cutoff,
                )
            )
            latencies: list[int] = []
            timestamps: list[_dt.datetime] = []

            for latency_ms, created_at in rows:
                latencies.append(int(latency_ms))
                if created_at:
                    timestamps.append(created_at)

        return _stats_from_samples(latencies, timestamps)

    async def async_get_global_latency_stats(self, days: int = 7) -> LatencyStats:
        """Get global latency statistics across all domains and models.

        Combines data from both CrawlResult (content extraction) and LLMCall
        (summarization) tables to get an overall latency distribution.

        Args:
            days: Number of days of history to consider

        Returns:
            LatencyStats with P50/P95 and sample count
        """

        cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)
        latencies: list[int] = []
        timestamps: list[_dt.datetime] = []
        async with self._database.session() as session:
            crawl_rows = await session.execute(
                select(CrawlResult.latency_ms, CrawlResult.updated_at).where(
                    CrawlResult.latency_ms.is_not(None),
                    CrawlResult.firecrawl_success.is_(True),
                    CrawlResult.updated_at >= cutoff,
                )
            )
            for latency_ms, updated_at in crawl_rows:
                latencies.append(int(latency_ms))
                if updated_at:
                    timestamps.append(updated_at)

            llm_rows = await session.execute(
                select(LLMCall.latency_ms, LLMCall.created_at).where(
                    LLMCall.latency_ms.is_not(None),
                    LLMCall.status == CallStatus.OK.value,
                    LLMCall.created_at >= cutoff,
                )
            )
            for latency_ms, created_at in llm_rows:
                latencies.append(int(latency_ms))
                if created_at:
                    timestamps.append(created_at)

        return _stats_from_samples(latencies, timestamps)

    async def async_get_combined_url_processing_stats(
        self, domain: str, days: int = 7
    ) -> LatencyStats:
        """Get combined latency statistics for full URL processing pipeline.

        Computes total processing time by summing crawl + LLM latencies
        for each request from the given domain.

        Args:
            domain: The domain to query
            days: Number of days of history to consider

        Returns:
            LatencyStats for total URL processing time
        """

        cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)
        combined_latencies: list[int] = []
        timestamps: list[_dt.datetime] = []
        expected_domain = domain.lower()

        async with self._database.session() as session:
            rows = await session.execute(
                select(
                    Request.id,
                    Request.normalized_url,
                    Request.updated_at,
                    func.coalesce(func.max(CrawlResult.latency_ms), 0).label("crawl_ms"),
                    func.coalesce(func.sum(LLMCall.latency_ms), 0).label("llm_ms"),
                )
                .outerjoin(
                    CrawlResult,
                    (CrawlResult.request_id == Request.id) & (CrawlResult.latency_ms.is_not(None)),
                )
                .outerjoin(
                    LLMCall,
                    (LLMCall.request_id == Request.id)
                    & (LLMCall.latency_ms.is_not(None))
                    & (LLMCall.status == CallStatus.OK.value),
                )
                .where(
                    Request.updated_at >= cutoff,
                    Request.status == RequestStatus.COMPLETED.value,
                )
                .group_by(Request.id, Request.normalized_url, Request.updated_at)
            )
            for _request_id, normalized_url, updated_at, crawl_ms, llm_ms in rows:
                if _extract_domain(normalized_url) != expected_domain:
                    continue
                total_ms = int(crawl_ms or 0) + int(llm_ms or 0)
                if total_ms <= 0:
                    continue
                combined_latencies.append(total_ms)
                if updated_at:
                    timestamps.append(updated_at)

        return _stats_from_samples(combined_latencies, timestamps)

    async def async_get_top_domains_by_latency(
        self, days: int = 7, limit: int = 20
    ) -> list[tuple[str, LatencyStats]]:
        """Get domains with highest P95 latency for analysis.

        Useful for identifying problematic domains that may need
        special timeout handling.

        Args:
            days: Number of days of history to consider
            limit: Maximum number of domains to return

        Returns:
            List of (domain, stats) tuples sorted by P95 descending
        """

        cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)
        async with self._database.session() as session:
            rows = await session.execute(
                select(CrawlResult.latency_ms, Request.normalized_url)
                .join(Request, CrawlResult.request_id == Request.id)
                .where(
                    CrawlResult.latency_ms.is_not(None),
                    CrawlResult.firecrawl_success.is_(True),
                    CrawlResult.updated_at >= cutoff,
                )
            )
            domain_latencies: dict[str, list[int]] = {}
            for latency_ms, normalized_url in rows:
                domain = _extract_domain(normalized_url)
                if domain:
                    domain_latencies.setdefault(domain, []).append(int(latency_ms))

        domain_stats: list[tuple[str, LatencyStats]] = []
        for domain, latencies in domain_latencies.items():
            if len(latencies) >= 3:
                stats = LatencyStats(
                    p50_ms=_compute_percentile(latencies, 0.5),
                    p95_ms=_compute_percentile(latencies, 0.95),
                    sample_count=len(latencies),
                )
                domain_stats.append((domain, stats))

        domain_stats.sort(key=lambda x: x[1].p95_ms or 0, reverse=True)
        return domain_stats[:limit]


def _stats_from_samples(
    latencies: list[int],
    timestamps: list[_dt.datetime],
) -> LatencyStats:
    if not latencies:
        return LatencyStats(
            p50_ms=None,
            p95_ms=None,
            sample_count=0,
        )

    return LatencyStats(
        p50_ms=_compute_percentile(latencies, 0.5),
        p95_ms=_compute_percentile(latencies, 0.95),
        sample_count=len(latencies),
        oldest_sample_ts=min(timestamps) if timestamps else None,
        newest_sample_ts=max(timestamps) if timestamps else None,
    )

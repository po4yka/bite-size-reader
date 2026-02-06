"""SQLite repository for latency statistics.

This repository queries CrawlResult and LLMCall tables to compute
P50/P95 latency statistics for adaptive timeout estimation.
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request
from app.infrastructure.persistence.sqlite.base import SqliteBaseRepository


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


def _extract_domain(url: str | None) -> str | None:
    """Extract domain from URL, normalizing www prefix."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower() if domain else None
    except Exception:
        return None


class SqliteLatencyStatsRepositoryAdapter(SqliteBaseRepository):
    """Repository for querying latency statistics from crawl results and LLM calls."""

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

        def _get() -> LatencyStats:
            cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)

            # Query crawl results with latency data for matching domain
            # Join with Request to filter by domain from normalized_url
            query = (
                CrawlResult.select(
                    CrawlResult.latency_ms, CrawlResult.updated_at, Request.normalized_url
                )
                .join(Request)
                .where(
                    CrawlResult.latency_ms.is_null(False),
                    CrawlResult.firecrawl_success == True,  # noqa: E712
                    CrawlResult.updated_at >= cutoff,
                )
            )

            # Filter by domain in Python since SQLite lacks efficient domain extraction
            latencies: list[int] = []
            timestamps: list[_dt.datetime] = []

            for result in query:
                url = result.request.normalized_url if hasattr(result, "request") else None
                extracted = _extract_domain(url)
                if extracted == domain.lower():
                    latencies.append(result.latency_ms)
                    if result.updated_at:
                        timestamps.append(result.updated_at)

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

        return await self._execute(_get, operation_name="get_domain_latency_stats", read_only=True)

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

        def _get() -> LatencyStats:
            cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)

            query = LLMCall.select(LLMCall.latency_ms, LLMCall.created_at).where(
                LLMCall.model == model,
                LLMCall.latency_ms.is_null(False),
                LLMCall.status == "success",
                LLMCall.created_at >= cutoff,
            )

            latencies: list[int] = []
            timestamps: list[_dt.datetime] = []

            for call in query:
                latencies.append(call.latency_ms)
                if call.created_at:
                    timestamps.append(call.created_at)

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

        return await self._execute(_get, operation_name="get_model_latency_stats", read_only=True)

    async def async_get_global_latency_stats(self, days: int = 7) -> LatencyStats:
        """Get global latency statistics across all domains and models.

        Combines data from both CrawlResult (content extraction) and LLMCall
        (summarization) tables to get an overall latency distribution.

        Args:
            days: Number of days of history to consider

        Returns:
            LatencyStats with P50/P95 and sample count
        """

        def _get() -> LatencyStats:
            cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)

            # Collect latencies from successful crawl results
            crawl_query = CrawlResult.select(CrawlResult.latency_ms, CrawlResult.updated_at).where(
                CrawlResult.latency_ms.is_null(False),
                CrawlResult.firecrawl_success == True,  # noqa: E712
                CrawlResult.updated_at >= cutoff,
            )

            latencies: list[int] = []
            timestamps: list[_dt.datetime] = []

            for result in crawl_query:
                latencies.append(result.latency_ms)
                if result.updated_at:
                    timestamps.append(result.updated_at)

            # Also include LLM call latencies for comprehensive view
            llm_query = LLMCall.select(LLMCall.latency_ms, LLMCall.created_at).where(
                LLMCall.latency_ms.is_null(False),
                LLMCall.status == "success",
                LLMCall.created_at >= cutoff,
            )

            for call in llm_query:
                latencies.append(call.latency_ms)
                if call.created_at:
                    timestamps.append(call.created_at)

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

        return await self._execute(_get, operation_name="get_global_latency_stats", read_only=True)

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

        def _get() -> LatencyStats:
            cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)

            # Query requests with both crawl and LLM data
            requests_query = Request.select(
                Request.id, Request.normalized_url, Request.updated_at
            ).where(
                Request.updated_at >= cutoff,
                Request.status == "completed",
            )

            combined_latencies: list[int] = []
            timestamps: list[_dt.datetime] = []

            for req in requests_query:
                extracted = _extract_domain(req.normalized_url)
                if extracted != domain.lower():
                    continue

                # Get crawl latency for this request
                crawl = CrawlResult.get_or_none(
                    CrawlResult.request == req.id,
                    CrawlResult.latency_ms.is_null(False),
                )
                crawl_ms = crawl.latency_ms if crawl else 0

                # Get total LLM latency for this request (may have multiple calls)
                llm_calls = LLMCall.select(LLMCall.latency_ms).where(
                    LLMCall.request == req.id,
                    LLMCall.latency_ms.is_null(False),
                    LLMCall.status == "success",
                )
                llm_ms = sum(call.latency_ms for call in llm_calls)

                if crawl_ms > 0 or llm_ms > 0:
                    combined_latencies.append(crawl_ms + llm_ms)
                    if req.updated_at:
                        timestamps.append(req.updated_at)

            if not combined_latencies:
                return LatencyStats(
                    p50_ms=None,
                    p95_ms=None,
                    sample_count=0,
                )

            return LatencyStats(
                p50_ms=_compute_percentile(combined_latencies, 0.5),
                p95_ms=_compute_percentile(combined_latencies, 0.95),
                sample_count=len(combined_latencies),
                oldest_sample_ts=min(timestamps) if timestamps else None,
                newest_sample_ts=max(timestamps) if timestamps else None,
            )

        return await self._execute(
            _get, operation_name="get_combined_url_processing_stats", read_only=True
        )

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

        def _get() -> list[tuple[str, LatencyStats]]:
            cutoff = _dt.datetime.now(UTC) - _dt.timedelta(days=days)

            # Collect latencies grouped by domain
            query = (
                CrawlResult.select(CrawlResult.latency_ms, Request.normalized_url)
                .join(Request)
                .where(
                    CrawlResult.latency_ms.is_null(False),
                    CrawlResult.firecrawl_success == True,  # noqa: E712
                    CrawlResult.updated_at >= cutoff,
                )
            )

            domain_latencies: dict[str, list[int]] = {}
            for result in query:
                url = result.request.normalized_url if hasattr(result, "request") else None
                domain = _extract_domain(url)
                if domain:
                    if domain not in domain_latencies:
                        domain_latencies[domain] = []
                    domain_latencies[domain].append(result.latency_ms)

            # Compute stats for each domain
            domain_stats: list[tuple[str, LatencyStats]] = []
            for domain, latencies in domain_latencies.items():
                if len(latencies) >= 3:  # Need at least 3 samples
                    stats = LatencyStats(
                        p50_ms=_compute_percentile(latencies, 0.5),
                        p95_ms=_compute_percentile(latencies, 0.95),
                        sample_count=len(latencies),
                    )
                    domain_stats.append((domain, stats))

            # Sort by P95 descending and take top N
            domain_stats.sort(key=lambda x: x[1].p95_ms or 0, reverse=True)
            return domain_stats[:limit]

        return await self._execute(
            _get, operation_name="get_top_domains_by_latency", read_only=True
        )

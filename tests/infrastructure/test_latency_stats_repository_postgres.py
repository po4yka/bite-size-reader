from __future__ import annotations

import datetime as dt
import os
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import delete

from app.config.database import DatabaseConfig
from app.core.call_status import CallStatus
from app.core.time_utils import UTC
from app.db.models import CrawlResult, LLMCall, Request
from app.db.session import Database
from app.domain.models.request import RequestStatus
from app.infrastructure.persistence.sqlite.repositories.latency_stats_repository import (
    SqliteLatencyStatsRepositoryAdapter,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _test_dsn() -> str:
    return os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
async def database() -> AsyncGenerator[Database]:
    dsn = _test_dsn()
    if not dsn:
        pytest.skip("TEST_DATABASE_URL is required for Postgres repository tests")

    db = Database(DatabaseConfig(dsn=dsn, pool_size=1, max_overflow=1))
    await db.migrate()
    await _clear(db)
    try:
        yield db
    finally:
        await _clear(db)
        await db.dispose()


async def _clear(database: Database) -> None:
    async with database.transaction() as session:
        await session.execute(delete(LLMCall))
        await session.execute(delete(CrawlResult))
        await session.execute(delete(Request))


async def _add_request_with_latency(
    database: Database,
    *,
    index: int,
    url: str,
    crawl_ms: int | None = None,
    llm_ms: list[int] | None = None,
    model: str = "model-a",
    created_at: dt.datetime | None = None,
    status: str = RequestStatus.COMPLETED.value,
    crawl_success: bool = True,
) -> None:
    timestamp = created_at or dt.datetime.now(UTC)
    async with database.transaction() as session:
        request = Request(
            type="url",
            status=status,
            correlation_id=f"latency-{index}",
            user_id=7000 + index,
            input_url=url,
            normalized_url=url,
            dedupe_hash=f"latency-{index}",
            updated_at=timestamp,
        )
        session.add(request)
        await session.flush()
        if crawl_ms is not None:
            session.add(
                CrawlResult(
                    request_id=request.id,
                    firecrawl_success=crawl_success,
                    latency_ms=crawl_ms,
                    updated_at=timestamp,
                )
            )
        for latency_ms in llm_ms or []:
            session.add(
                LLMCall(
                    request_id=request.id,
                    provider="openrouter",
                    model=model,
                    status=CallStatus.OK.value,
                    latency_ms=latency_ms,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )


@pytest.mark.asyncio
async def test_latency_stats_repository_reads_domain_model_and_global_stats(
    database: Database,
) -> None:
    repo = SqliteLatencyStatsRepositoryAdapter(database)
    now = dt.datetime.now(UTC)

    await _add_request_with_latency(
        database,
        index=1,
        url="https://example.com/a",
        crawl_ms=100,
        llm_ms=[50],
        created_at=now - dt.timedelta(hours=2),
    )
    await _add_request_with_latency(
        database,
        index=2,
        url="https://example.com/b",
        crawl_ms=200,
        llm_ms=[150],
        created_at=now - dt.timedelta(hours=1),
    )
    await _add_request_with_latency(
        database,
        index=3,
        url="https://other.test/c",
        crawl_ms=400,
        llm_ms=[600],
        model="model-b",
    )
    await _add_request_with_latency(
        database,
        index=4,
        url="https://example.com/old",
        crawl_ms=999,
        llm_ms=[999],
        created_at=now - dt.timedelta(days=10),
    )
    await _add_request_with_latency(
        database,
        index=5,
        url="https://example.com/failed",
        crawl_ms=888,
        crawl_success=False,
    )

    domain_stats = await repo.async_get_domain_latency_stats("example.com")
    assert domain_stats.sample_count == 2
    assert domain_stats.p50_ms == 150.0
    assert domain_stats.p95_ms == 195.0
    assert domain_stats.oldest_sample_ts is not None
    assert domain_stats.newest_sample_ts is not None

    model_stats = await repo.async_get_model_latency_stats("model-a")
    assert model_stats.sample_count == 2
    assert model_stats.p50_ms == 100.0

    global_stats = await repo.async_get_global_latency_stats()
    assert global_stats.sample_count == 6
    assert global_stats.p50_ms == 175.0


@pytest.mark.asyncio
async def test_latency_stats_repository_reads_combined_and_top_domain_stats(
    database: Database,
) -> None:
    repo = SqliteLatencyStatsRepositoryAdapter(database)

    await _add_request_with_latency(
        database,
        index=11,
        url="https://slow.test/a",
        crawl_ms=500,
        llm_ms=[100, 100],
    )
    await _add_request_with_latency(
        database,
        index=12,
        url="https://slow.test/b",
        crawl_ms=700,
        llm_ms=[100],
    )
    await _add_request_with_latency(
        database,
        index=13,
        url="https://slow.test/c",
        crawl_ms=900,
        llm_ms=[100],
    )
    await _add_request_with_latency(
        database,
        index=14,
        url="https://fast.test/a",
        crawl_ms=100,
    )
    await _add_request_with_latency(
        database,
        index=15,
        url="https://fast.test/b",
        crawl_ms=110,
    )
    await _add_request_with_latency(
        database,
        index=16,
        url="https://fast.test/c",
        crawl_ms=120,
    )

    combined = await repo.async_get_combined_url_processing_stats("slow.test")
    assert combined.sample_count == 3
    assert combined.p50_ms == 800.0
    assert combined.p95_ms == 980.0

    top_domains = await repo.async_get_top_domains_by_latency(limit=2)
    assert [domain for domain, _stats in top_domains] == ["slow.test", "fast.test"]
    assert top_domains[0][1].sample_count == 3
    assert top_domains[0][1].p95_ms == 880.0

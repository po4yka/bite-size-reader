from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.adapters.content.content_chunker import ContentChunker
from app.core.summary_aggregate import aggregate_chunk_summaries


def _make_chunker() -> ContentChunker:
    cfg = cast("Any", SimpleNamespace(runtime=SimpleNamespace(), openrouter=SimpleNamespace()))
    return ContentChunker(
        cfg=cfg,
        openrouter=MagicMock(),
        response_formatter=MagicMock(),
        audit_func=MagicMock(),
        sem=MagicMock(),
    )


@pytest.mark.asyncio
async def test_resolve_aggregated_summary_uses_python_when_shadow_disabled() -> None:
    chunker = _make_chunker()
    chunk_summaries = [
        {"summary_250": "A summary", "estimated_reading_time_min": 1},
        {"summary_250": "B summary", "estimated_reading_time_min": 2},
    ]

    result = await chunker._resolve_aggregated_summary(
        chunk_summaries=chunk_summaries,
        req_id=1,
        correlation_id="cid",
    )

    assert result == aggregate_chunk_summaries(chunk_summaries)


@pytest.mark.asyncio
async def test_resolve_aggregated_summary_uses_rust_when_shadow_enabled() -> None:
    chunker = _make_chunker()
    chunker.pipeline_shadow = MagicMock()
    chunker.pipeline_shadow.options.enabled = True
    chunker.pipeline_shadow.resolve_summary_aggregate = AsyncMock(
        return_value={"summary_250": "Rust aggregate"}
    )

    result = await chunker._resolve_aggregated_summary(
        chunk_summaries=[{"summary_250": "A"}],
        req_id=2,
        correlation_id="cid",
    )

    assert result == {"summary_250": "Rust aggregate"}
    chunker.pipeline_shadow.resolve_summary_aggregate.assert_called_once_with(
        correlation_id="cid",
        request_id=2,
        summaries=[{"summary_250": "A"}],
    )

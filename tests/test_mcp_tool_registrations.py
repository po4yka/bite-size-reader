from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.mcp.tool_registrations import register_tools

if TYPE_CHECKING:
    from collections.abc import Callable


class RecordingMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, *_args, **_kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


@pytest.mark.asyncio
async def test_mcp_tool_registration_records_success_metrics() -> None:
    mcp = RecordingMCP()
    aggregation_service = SimpleNamespace(
        create_aggregation_bundle=AsyncMock(return_value={"session": {"id": 1}}),
        get_aggregation_bundle=AsyncMock(return_value={"session": {"id": 1}}),
        list_aggregation_bundles=AsyncMock(return_value={"sessions": []}),
        check_source_supported=MagicMock(return_value={"supported": True}),
    )
    article_service = SimpleNamespace(
        search_articles=MagicMock(return_value={"items": []}),
        get_article=MagicMock(return_value={"id": 1}),
        list_articles=MagicMock(return_value={"items": []}),
        get_article_content=MagicMock(return_value={"content": "body"}),
        get_stats=MagicMock(return_value={"total": 1}),
        find_by_entity=MagicMock(return_value={"items": []}),
        check_url=MagicMock(return_value={"duplicate": False}),
    )
    catalog_service = SimpleNamespace(
        list_collections=MagicMock(return_value={"items": []}),
        get_collection=MagicMock(return_value={"id": 1}),
        list_videos=MagicMock(return_value={"items": []}),
        get_video_transcript=MagicMock(return_value={"video_id": "abc"}),
    )
    semantic_service = SimpleNamespace(
        semantic_search=AsyncMock(return_value={"items": []}),
        hybrid_search=AsyncMock(return_value={"items": []}),
        find_similar_articles=AsyncMock(return_value={"items": []}),
        chroma_health=AsyncMock(return_value={"status": "ok"}),
        chroma_index_stats=AsyncMock(return_value={"coverage": 1.0}),
        chroma_sync_gap=AsyncMock(return_value={"gap": 0}),
    )

    register_tools(
        mcp,
        aggregation_service=cast("Any", aggregation_service),
        article_service=cast("Any", article_service),
        catalog_service=cast("Any", catalog_service),
        semantic_service=cast("Any", semantic_service),
    )

    with patch("app.mcp.tool_registrations.record_request") as metrics_mock:
        payload = await mcp.tools["create_aggregation_bundle"](
            items=[{"type": "url", "url": "https://example.com"}]
        )

    assert json.loads(payload)["session"]["id"] == 1
    metrics_mock.assert_called_once()
    metric_kwargs = metrics_mock.call_args.kwargs
    assert metric_kwargs["request_type"] == "create_aggregation_bundle"
    assert metric_kwargs["status"] == "success"
    assert metric_kwargs["source"] == "mcp"
    assert metric_kwargs["latency_seconds"] >= 0


@pytest.mark.asyncio
async def test_mcp_tool_registration_records_error_metrics_for_service_errors() -> None:
    mcp = RecordingMCP()
    aggregation_service = SimpleNamespace(
        create_aggregation_bundle=AsyncMock(return_value={"error": "Access denied"}),
        get_aggregation_bundle=AsyncMock(return_value={"error": "Access denied"}),
        list_aggregation_bundles=AsyncMock(return_value={"sessions": []}),
        check_source_supported=MagicMock(return_value={"supported": True}),
    )
    article_service = SimpleNamespace(
        search_articles=MagicMock(side_effect=RuntimeError("boom")),
        get_article=MagicMock(return_value={"id": 1}),
        list_articles=MagicMock(return_value={"items": []}),
        get_article_content=MagicMock(return_value={"content": "body"}),
        get_stats=MagicMock(return_value={"total": 1}),
        find_by_entity=MagicMock(return_value={"items": []}),
        check_url=MagicMock(return_value={"duplicate": False}),
    )
    catalog_service = SimpleNamespace(
        list_collections=MagicMock(return_value={"items": []}),
        get_collection=MagicMock(return_value={"id": 1}),
        list_videos=MagicMock(return_value={"items": []}),
        get_video_transcript=MagicMock(return_value={"video_id": "abc"}),
    )
    semantic_service = SimpleNamespace(
        semantic_search=AsyncMock(return_value={"items": []}),
        hybrid_search=AsyncMock(return_value={"items": []}),
        find_similar_articles=AsyncMock(return_value={"items": []}),
        chroma_health=AsyncMock(return_value={"status": "ok"}),
        chroma_index_stats=AsyncMock(return_value={"coverage": 1.0}),
        chroma_sync_gap=AsyncMock(return_value={"gap": 0}),
    )

    register_tools(
        mcp,
        aggregation_service=cast("Any", aggregation_service),
        article_service=cast("Any", article_service),
        catalog_service=cast("Any", catalog_service),
        semantic_service=cast("Any", semantic_service),
    )

    with patch("app.mcp.tool_registrations.record_request") as metrics_mock:
        payload = await mcp.tools["create_aggregation_bundle"](
            items=[{"type": "url", "url": "https://example.com"}]
        )

    assert json.loads(payload)["error"] == "Access denied"
    metric_kwargs = metrics_mock.call_args.kwargs
    assert metric_kwargs["request_type"] == "create_aggregation_bundle"
    assert metric_kwargs["status"] == "error"
    assert metric_kwargs["source"] == "mcp"
    assert metric_kwargs["latency_seconds"] >= 0

    with patch("app.mcp.tool_registrations.record_request") as metrics_mock:
        with pytest.raises(RuntimeError, match="boom"):
            mcp.tools["search_articles"]("query", 5)

    metric_kwargs = metrics_mock.call_args.kwargs
    assert metric_kwargs["request_type"] == "search_articles"
    assert metric_kwargs["status"] == "error"
    assert metric_kwargs["source"] == "mcp"
    assert metric_kwargs["latency_seconds"] >= 0

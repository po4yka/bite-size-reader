"""MCP tool registration adapters — thin wrappers required by the MCP framework.

Each function is a single-line adapter: decorate the service call with @mcp.tool()
and serialize the result to JSON for the wire protocol. No domain logic lives here;
all business logic is in the injected service classes.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from app.mcp.helpers import to_json
from app.observability.metrics import record_request

if TYPE_CHECKING:
    from app.mcp.aggregation_service import AggregationMcpService
    from app.mcp.article_service import ArticleReadService
    from app.mcp.catalog_service import CatalogReadService
    from app.mcp.semantic_service import SemanticSearchService
    from app.mcp.signal_service import SignalMcpService


def register_tools(
    mcp: Any,
    *,
    aggregation_service: AggregationMcpService,
    article_service: ArticleReadService,
    catalog_service: CatalogReadService,
    semantic_service: SemanticSearchService,
    signal_service: SignalMcpService | None = None,
) -> None:
    signal_runtime: Any = signal_service if signal_service is not None else _NullSignalService()

    def _status_from_result(result: Any) -> str:
        return "error" if isinstance(result, dict) and "error" in result else "success"

    def _record_tool_metric(tool_name: str, *, status: str, started_at: float) -> None:
        record_request(
            request_type=tool_name,
            status=status,
            source="mcp",
            latency_seconds=max(0.0, time.perf_counter() - started_at),
        )

    async def _call_async(tool_name: str, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        started_at = time.perf_counter()
        try:
            result = await fn(*args, **kwargs)
        except Exception:
            _record_tool_metric(tool_name, status="error", started_at=started_at)
            raise
        _record_tool_metric(tool_name, status=_status_from_result(result), started_at=started_at)
        return result

    def _call_sync(tool_name: str, fn: Any, /, *args: Any, **kwargs: Any) -> Any:
        started_at = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
        except Exception:
            _record_tool_metric(tool_name, status="error", started_at=started_at)
            raise
        _record_tool_metric(tool_name, status=_status_from_result(result), started_at=started_at)
        return result

    @mcp.tool()
    async def create_aggregation_bundle(
        items: list[dict[str, Any]],
        lang_preference: str = "auto",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create and run an aggregation bundle for the scoped MCP user."""
        return to_json(
            await _call_async(
                "create_aggregation_bundle",
                aggregation_service.create_aggregation_bundle,
                items=items,
                lang_preference=lang_preference,
                metadata=metadata,
            )
        )

    @mcp.tool()
    async def get_aggregation_bundle(session_id: int) -> str:
        """Get one persisted aggregation bundle by session ID."""
        return to_json(
            await _call_async(
                "get_aggregation_bundle",
                aggregation_service.get_aggregation_bundle,
                session_id,
            )
        )

    @mcp.tool()
    async def list_aggregation_bundles(
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> str:
        """List aggregation bundles for the scoped MCP user."""
        return to_json(
            await _call_async(
                "list_aggregation_bundles",
                aggregation_service.list_aggregation_bundles,
                limit=limit,
                offset=offset,
                status=status,
            )
        )

    @mcp.tool()
    def check_source_supported(url: str, source_kind_hint: str | None = None) -> str:
        """Classify whether a URL fits the public aggregation source contract."""
        return to_json(
            _call_sync(
                "check_source_supported",
                aggregation_service.check_source_supported,
                url=url,
                source_kind_hint=source_kind_hint,
            )
        )

    @mcp.tool()
    async def search_articles(query: str, limit: int = 10) -> str:
        """Search stored article summaries by keyword, topic, or entity."""
        return to_json(
            await _call_async("search_articles", article_service.search_articles, query, limit)
        )

    @mcp.tool()
    async def get_article(summary_id: int) -> str:
        """Get full details of an article summary by its ID."""
        return to_json(await _call_async("get_article", article_service.get_article, summary_id))

    @mcp.tool()
    async def list_articles(
        limit: int = 20,
        offset: int = 0,
        is_favorited: bool | None = None,
        lang: str | None = None,
        tag: str | None = None,
    ) -> str:
        """List stored article summaries with optional filters."""
        return to_json(
            await _call_async(
                "list_articles",
                article_service.list_articles,
                limit,
                offset,
                is_favorited,
                lang,
                tag,
            )
        )

    @mcp.tool()
    async def get_article_content(summary_id: int) -> str:
        """Get the full extracted content (markdown/text) of an article."""
        return to_json(
            await _call_async(
                "get_article_content", article_service.get_article_content, summary_id
            )
        )

    @mcp.tool()
    async def get_stats() -> str:
        """Get statistics about the Ratatoskr article database."""
        return to_json(await _call_async("get_stats", article_service.get_stats))

    @mcp.tool()
    async def find_by_entity(
        entity_name: str, entity_type: str | None = None, limit: int = 10
    ) -> str:
        """Find articles that mention a specific entity."""
        return to_json(
            await _call_async(
                "find_by_entity", article_service.find_by_entity, entity_name, entity_type, limit
            )
        )

    @mcp.tool()
    async def list_collections(limit: int = 20, offset: int = 0) -> str:
        """List article collections (folders/reading lists)."""
        return to_json(
            await _call_async("list_collections", catalog_service.list_collections, limit, offset)
        )

    @mcp.tool()
    async def get_collection(
        collection_id: int, include_items: bool = True, limit: int = 50
    ) -> str:
        """Get details of a specific collection and its article summaries."""
        return to_json(
            await _call_async(
                "get_collection",
                catalog_service.get_collection,
                collection_id,
                include_items,
                limit,
            )
        )

    @mcp.tool()
    async def list_videos(limit: int = 20, offset: int = 0, status: str | None = None) -> str:
        """List downloaded YouTube videos with metadata."""
        return to_json(
            await _call_async("list_videos", catalog_service.list_videos, limit, offset, status)
        )

    @mcp.tool()
    async def get_video_transcript(video_id: str) -> str:
        """Get the transcript text of a downloaded YouTube video."""
        return to_json(
            await _call_async(
                "get_video_transcript", catalog_service.get_video_transcript, video_id
            )
        )

    @mcp.tool()
    async def check_url(url: str) -> str:
        """Check if a URL has already been processed and summarised."""
        return to_json(await _call_async("check_url", article_service.check_url, url))

    @mcp.tool()
    async def semantic_search(
        description: str,
        limit: int = 10,
        language: str | None = None,
        min_similarity: float = 0.25,
        rerank: bool = False,
        include_chunks: bool = True,
    ) -> str:
        """Search articles by semantic meaning with resilient fallback strategy."""
        return to_json(
            await _call_async(
                "semantic_search",
                semantic_service.semantic_search,
                description,
                limit=limit,
                language=language,
                min_similarity=min_similarity,
                rerank=rerank,
                include_chunks=include_chunks,
            )
        )

    @mcp.tool()
    async def hybrid_search(
        query: str,
        limit: int = 10,
        language: str | None = None,
        min_similarity: float = 0.25,
        rerank: bool = False,
    ) -> str:
        """Combine keyword and semantic retrieval into a single ranked result list."""
        return to_json(
            await _call_async(
                "hybrid_search",
                semantic_service.hybrid_search,
                query,
                limit=limit,
                language=language,
                min_similarity=min_similarity,
                rerank=rerank,
            )
        )

    @mcp.tool()
    async def find_similar_articles(
        summary_id: int,
        limit: int = 10,
        min_similarity: float = 0.3,
        rerank: bool = False,
        include_chunks: bool = True,
    ) -> str:
        """Find articles semantically similar to an existing summary."""
        return to_json(
            await _call_async(
                "find_similar_articles",
                semantic_service.find_similar_articles,
                summary_id,
                limit=limit,
                min_similarity=min_similarity,
                rerank=rerank,
                include_chunks=include_chunks,
            )
        )

    @mcp.tool()
    async def list_signal_sources(limit: int = 50) -> str:
        """List signal sources for the scoped MCP user."""
        return to_json(await _call_async("list_signal_sources", signal_runtime.list_sources, limit))

    @mcp.tool()
    async def list_user_signals(limit: int = 20, status: str | None = None) -> str:
        """List scored signal candidates for the scoped MCP user."""
        return to_json(
            await _call_async("list_user_signals", signal_runtime.list_signals, limit, status)
        )

    @mcp.tool()
    async def update_signal_feedback(signal_id: int, action: str) -> str:
        """Write signal feedback: like, dislike, skip, queue, or hide_source."""
        return to_json(
            await _call_async(
                "update_signal_feedback",
                signal_runtime.update_signal_feedback,
                signal_id,
                action,
            )
        )

    @mcp.tool()
    async def set_signal_source_active(source_id: int, is_active: bool) -> str:
        """Enable or disable one subscribed signal source for the scoped MCP user."""
        return to_json(
            await _call_async(
                "set_signal_source_active",
                signal_runtime.set_source_active,
                source_id,
                is_active,
            )
        )

    @mcp.tool()
    async def vector_health() -> str:
        """Check vector store availability and fallback readiness."""
        return to_json(await _call_async("vector_health", semantic_service.vector_health))

    @mcp.tool()
    async def vector_index_stats(scan_limit: int = 5000) -> str:
        """Return index coverage stats between database summaries and the vector store."""
        return to_json(
            await _call_async("vector_index_stats", semantic_service.vector_index_stats, scan_limit)
        )

    @mcp.tool()
    async def vector_sync_gap(max_scan: int = 5000, sample_size: int = 20) -> str:
        """Report sync gaps between database summaries and the vector store index."""
        return to_json(
            await _call_async(
                "vector_sync_gap",
                semantic_service.vector_sync_gap,
                max_scan,
                sample_size,
            )
        )


class _NullSignalService:
    async def list_sources(self, limit: int = 50) -> dict[str, Any]:
        return {"sources": []}

    async def list_signals(self, limit: int = 20, status: str | None = None) -> dict[str, Any]:
        return {"signals": []}

    async def update_signal_feedback(self, signal_id: int, action: str) -> dict[str, Any]:
        return {"error": "Signal service is not configured"}

    async def set_source_active(self, source_id: int, is_active: bool) -> dict[str, Any]:
        return {"error": "Signal service is not configured"}

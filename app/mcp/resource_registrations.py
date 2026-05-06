"""MCP resource registration adapters — thin wrappers required by the MCP framework.

Each function is a single-line adapter: decorate the service call with @mcp.resource()
and serialize the result to JSON for the wire protocol. No domain logic lives here;
all business logic is in the injected service classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.mcp.helpers import to_json

if TYPE_CHECKING:
    from app.mcp.aggregation_service import AggregationMcpService
    from app.mcp.article_service import ArticleReadService
    from app.mcp.catalog_service import CatalogReadService
    from app.mcp.semantic_service import SemanticSearchService
    from app.mcp.signal_service import SignalMcpService


def register_resources(
    mcp: Any,
    *,
    aggregation_service: AggregationMcpService,
    article_service: ArticleReadService,
    catalog_service: CatalogReadService,
    semantic_service: SemanticSearchService,
    signal_service: SignalMcpService | None = None,
) -> None:
    signal_runtime: Any = signal_service if signal_service is not None else _NullSignalService()

    @mcp.resource("ratatoskr://aggregations/recent")
    async def recent_aggregations_resource() -> str:
        """Recent aggregation bundles for the scoped MCP user."""
        return to_json(await aggregation_service.list_aggregation_bundles(limit=10, offset=0))

    @mcp.resource("ratatoskr://aggregations/{session_id}")
    async def aggregation_bundle_resource(session_id: str) -> str:
        """One persisted aggregation bundle for the scoped MCP user."""
        try:
            resolved_session_id = int(session_id)
        except ValueError:
            return to_json({"error": f"Invalid aggregation session ID: {session_id}"})
        return to_json(await aggregation_service.get_aggregation_bundle(resolved_session_id))

    @mcp.resource("ratatoskr://articles/recent")
    def recent_articles_resource() -> str:
        """A snapshot of the 10 most recent article summaries."""
        return to_json(article_service.list_articles(limit=10, offset=0))

    @mcp.resource("ratatoskr://articles/favorites")
    def favorites_resource() -> str:
        """All favorited article summaries."""
        return to_json(article_service.list_articles(limit=50, offset=0, is_favorited=True))

    @mcp.resource("ratatoskr://articles/unread")
    def unread_resource() -> str:
        """Unread article summaries (up to 20)."""
        return to_json(article_service.unread_articles(limit=20))

    @mcp.resource("ratatoskr://stats")
    def stats_resource() -> str:
        """Current database statistics for Ratatoskr."""
        return to_json(article_service.get_stats())

    @mcp.resource("ratatoskr://tags")
    def tags_resource() -> str:
        """All topic tags with article counts, sorted by frequency."""
        return to_json(article_service.tag_counts())

    @mcp.resource("ratatoskr://entities")
    def entities_resource() -> str:
        """Aggregated entities (people, organizations, locations) across all articles."""
        return to_json(article_service.entity_counts())

    @mcp.resource("ratatoskr://domains")
    def domains_resource() -> str:
        """Source domains with article counts, sorted by frequency."""
        return to_json(article_service.domain_counts())

    @mcp.resource("ratatoskr://collections")
    def collections_resource() -> str:
        """All top-level collections with item counts."""
        return to_json(catalog_service.list_collections(limit=50, offset=0))

    @mcp.resource("ratatoskr://videos/recent")
    def recent_videos_resource() -> str:
        """10 most recent video downloads with metadata."""
        return to_json(catalog_service.list_videos(limit=10, offset=0, status="completed"))

    @mcp.resource("ratatoskr://processing/stats")
    def processing_stats_resource() -> str:
        """Processing statistics: LLM call counts, token usage, model breakdown."""
        return to_json(catalog_service.processing_stats())

    @mcp.resource("ratatoskr://vector/health")
    async def vector_health_resource() -> str:
        """Vector store availability status for semantic MCP tools."""
        return to_json(await semantic_service.vector_health())

    @mcp.resource("ratatoskr://vector/index-stats")
    async def vector_index_stats_resource() -> str:
        """Vector store index coverage compared to SQLite summaries."""
        return to_json(await semantic_service.vector_index_stats())

    @mcp.resource("ratatoskr://vector/sync-gap")
    async def vector_sync_gap_resource() -> str:
        """Vector store/SQLite sync gap sample using default scan limits."""
        return to_json(await semantic_service.vector_sync_gap())

    @mcp.resource("ratatoskr://signals/recent")
    async def recent_signals_resource() -> str:
        """Recent signal candidates for the scoped MCP user."""
        return to_json(await signal_runtime.list_signals(limit=20))

    @mcp.resource("ratatoskr://sources")
    async def signal_sources_resource() -> str:
        """Signal source catalog."""
        return to_json(await signal_runtime.list_sources(limit=100))


class _NullSignalService:
    async def list_sources(self, limit: int = 50) -> dict[str, Any]:
        return {"sources": []}

    async def list_signals(self, limit: int = 20, status: str | None = None) -> dict[str, Any]:
        return {"signals": []}

"""MCP resource registration adapters — thin wrappers required by the MCP framework.

Each function is a single-line adapter: decorate the service call with @mcp.resource()
and serialize the result to JSON for the wire protocol. No domain logic lives here;
all business logic is in the injected service classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.mcp.helpers import to_json

if TYPE_CHECKING:
    from app.mcp.article_service import ArticleReadService
    from app.mcp.catalog_service import CatalogReadService
    from app.mcp.semantic_service import SemanticSearchService


def register_resources(
    mcp: Any,
    *,
    article_service: ArticleReadService,
    catalog_service: CatalogReadService,
    semantic_service: SemanticSearchService,
) -> None:
    @mcp.resource("bsr://articles/recent")
    def recent_articles_resource() -> str:
        """A snapshot of the 10 most recent article summaries."""
        return to_json(article_service.list_articles(limit=10, offset=0))

    @mcp.resource("bsr://articles/favorites")
    def favorites_resource() -> str:
        """All favorited article summaries."""
        return to_json(article_service.list_articles(limit=50, offset=0, is_favorited=True))

    @mcp.resource("bsr://articles/unread")
    def unread_resource() -> str:
        """Unread article summaries (up to 20)."""
        return to_json(article_service.unread_articles(limit=20))

    @mcp.resource("bsr://stats")
    def stats_resource() -> str:
        """Current database statistics for Bite-Size Reader."""
        return to_json(article_service.get_stats())

    @mcp.resource("bsr://tags")
    def tags_resource() -> str:
        """All topic tags with article counts, sorted by frequency."""
        return to_json(article_service.tag_counts())

    @mcp.resource("bsr://entities")
    def entities_resource() -> str:
        """Aggregated entities (people, organizations, locations) across all articles."""
        return to_json(article_service.entity_counts())

    @mcp.resource("bsr://domains")
    def domains_resource() -> str:
        """Source domains with article counts, sorted by frequency."""
        return to_json(article_service.domain_counts())

    @mcp.resource("bsr://collections")
    def collections_resource() -> str:
        """All top-level collections with item counts."""
        return to_json(catalog_service.list_collections(limit=50, offset=0))

    @mcp.resource("bsr://videos/recent")
    def recent_videos_resource() -> str:
        """10 most recent video downloads with metadata."""
        return to_json(catalog_service.list_videos(limit=10, offset=0, status="completed"))

    @mcp.resource("bsr://processing/stats")
    def processing_stats_resource() -> str:
        """Processing statistics: LLM call counts, token usage, model breakdown."""
        return to_json(catalog_service.processing_stats())

    @mcp.resource("bsr://chroma/health")
    async def chroma_health_resource() -> str:
        """Chroma availability status for semantic MCP tools."""
        return to_json(await semantic_service.chroma_health())

    @mcp.resource("bsr://chroma/index-stats")
    async def chroma_index_stats_resource() -> str:
        """Chroma index coverage compared to SQLite summaries."""
        return to_json(await semantic_service.chroma_index_stats())

    @mcp.resource("bsr://chroma/sync-gap")
    async def chroma_sync_gap_resource() -> str:
        """Chroma/SQLite sync gap sample using default scan limits."""
        return to_json(await semantic_service.chroma_sync_gap())

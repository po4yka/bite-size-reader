from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.mcp.helpers import to_json

if TYPE_CHECKING:
    from app.mcp.article_service import ArticleReadService
    from app.mcp.catalog_service import CatalogReadService
    from app.mcp.semantic_service import SemanticSearchService


def register_tools(
    mcp: Any,
    *,
    article_service: ArticleReadService,
    catalog_service: CatalogReadService,
    semantic_service: SemanticSearchService,
) -> None:
    @mcp.tool()
    def search_articles(query: str, limit: int = 10) -> str:
        """Search stored article summaries by keyword, topic, or entity."""
        return to_json(article_service.search_articles(query, limit))

    @mcp.tool()
    def get_article(summary_id: int) -> str:
        """Get full details of an article summary by its ID."""
        return to_json(article_service.get_article(summary_id))

    @mcp.tool()
    def list_articles(
        limit: int = 20,
        offset: int = 0,
        is_favorited: bool | None = None,
        lang: str | None = None,
        tag: str | None = None,
    ) -> str:
        """List stored article summaries with optional filters."""
        return to_json(article_service.list_articles(limit, offset, is_favorited, lang, tag))

    @mcp.tool()
    def get_article_content(summary_id: int) -> str:
        """Get the full extracted content (markdown/text) of an article."""
        return to_json(article_service.get_article_content(summary_id))

    @mcp.tool()
    def get_stats() -> str:
        """Get statistics about the Bite-Size Reader article database."""
        return to_json(article_service.get_stats())

    @mcp.tool()
    def find_by_entity(entity_name: str, entity_type: str | None = None, limit: int = 10) -> str:
        """Find articles that mention a specific entity."""
        return to_json(article_service.find_by_entity(entity_name, entity_type, limit))

    @mcp.tool()
    def list_collections(limit: int = 20, offset: int = 0) -> str:
        """List article collections (folders/reading lists)."""
        return to_json(catalog_service.list_collections(limit, offset))

    @mcp.tool()
    def get_collection(collection_id: int, include_items: bool = True, limit: int = 50) -> str:
        """Get details of a specific collection and its article summaries."""
        return to_json(catalog_service.get_collection(collection_id, include_items, limit))

    @mcp.tool()
    def list_videos(limit: int = 20, offset: int = 0, status: str | None = None) -> str:
        """List downloaded YouTube videos with metadata."""
        return to_json(catalog_service.list_videos(limit, offset, status))

    @mcp.tool()
    def get_video_transcript(video_id: str) -> str:
        """Get the transcript text of a downloaded YouTube video."""
        return to_json(catalog_service.get_video_transcript(video_id))

    @mcp.tool()
    def check_url(url: str) -> str:
        """Check if a URL has already been processed and summarised."""
        return to_json(article_service.check_url(url))

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
            await semantic_service.semantic_search(
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
            await semantic_service.hybrid_search(
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
            await semantic_service.find_similar_articles(
                summary_id,
                limit=limit,
                min_similarity=min_similarity,
                rerank=rerank,
                include_chunks=include_chunks,
            )
        )

    @mcp.tool()
    async def chroma_health() -> str:
        """Check Chroma availability and fallback readiness."""
        return to_json(await semantic_service.chroma_health())

    @mcp.tool()
    async def chroma_index_stats(scan_limit: int = 5000) -> str:
        """Return index coverage stats between SQLite summaries and Chroma."""
        return to_json(await semantic_service.chroma_index_stats(scan_limit))

    @mcp.tool()
    async def chroma_sync_gap(max_scan: int = 5000, sample_size: int = 20) -> str:
        """Report sync gaps between SQLite summaries and Chroma index."""
        return to_json(await semantic_service.chroma_sync_gap(max_scan, sample_size))

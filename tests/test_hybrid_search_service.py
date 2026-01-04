"""Tests for the HybridSearchService."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services.hybrid_search_service import HybridSearchService
from app.services.topic_search import TopicArticle


class FakeVectorResult:
    """Mock vector search result."""

    def __init__(self, url: str, title: str, snippet: str, similarity_score: float):
        self.url = url
        self.title = title
        self.snippet = snippet
        self.text = snippet
        self.source = "example.com"
        self.published_at = "2024-01-01"
        self.similarity_score = similarity_score


def _wrap_vector_results(results: list[FakeVectorResult]) -> SimpleNamespace:
    """Wrap results in a ChromaVectorSearchResults-like object."""
    return SimpleNamespace(results=results, has_more=False)


class TestHybridSearchService(unittest.IsolatedAsyncioTestCase):
    """Test cases for HybridSearchService."""

    async def test_hybrid_search_combines_fts_and_vector_results(self):
        """Test that hybrid search combines FTS and vector results."""
        # Mock FTS service
        fts_service = AsyncMock()
        fts_service.find_articles.return_value = [
            TopicArticle(
                title="FTS Result 1",
                url="https://example.com/fts1",
                snippet="FTS snippet 1",
                source="example.com",
                published_at="2024-01-01",
            ),
            TopicArticle(
                title="FTS Result 2",
                url="https://example.com/fts2",
                snippet="FTS snippet 2",
                source="example.com",
                published_at="2024-01-02",
            ),
        ]

        # Mock vector service
        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results(
            [
                FakeVectorResult(
                    url="https://example.com/vec1",
                    title="Vector Result 1",
                    snippet="Vector snippet 1",
                    similarity_score=0.9,
                ),
                FakeVectorResult(
                    url="https://example.com/vec2",
                    title="Vector Result 2",
                    snippet="Vector snippet 2",
                    similarity_score=0.8,
                ),
            ]
        )

        # Create hybrid service
        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=10,
        )

        # Perform search
        results = await hybrid_service.search("test query")

        # Verify both services were called
        fts_service.find_articles.assert_awaited_once()
        vector_service.search.assert_awaited_once()

        # Verify results are combined (4 unique URLs)
        assert len(results) == 4
        urls = {r.url for r in results}
        assert "https://example.com/fts1" in urls
        assert "https://example.com/fts2" in urls
        assert "https://example.com/vec1" in urls
        assert "https://example.com/vec2" in urls

    async def test_hybrid_search_handles_overlapping_results(self):
        """Test that overlapping results from FTS and vector are merged correctly."""
        # Create overlapping result (same URL in both FTS and vector)
        overlap_url = "https://example.com/overlap"

        fts_service = AsyncMock()
        fts_service.find_articles.return_value = [
            TopicArticle(
                title="Overlapping Article",
                url=overlap_url,
                snippet="FTS snippet",
                source="example.com",
                published_at="2024-01-01",
            ),
        ]

        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results(
            [
                FakeVectorResult(
                    url=overlap_url,
                    title="Overlapping Article",
                    snippet="Vector snippet",
                    similarity_score=0.95,
                ),
            ]
        )

        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=10,
        )

        results = await hybrid_service.search("test query")

        # Only one result (merged)
        assert len(results) == 1
        assert results[0].url == overlap_url

    async def test_hybrid_search_respects_max_results(self):
        """Test that hybrid search limits results to max_results."""
        # Create many results
        fts_results = [
            TopicArticle(
                title=f"FTS {i}",
                url=f"https://example.com/fts{i}",
                snippet=f"Snippet {i}",
                source="example.com",
                published_at="2024-01-01",
            )
            for i in range(20)
        ]

        vector_results = [
            FakeVectorResult(
                url=f"https://example.com/vec{i}",
                title=f"Vector {i}",
                snippet=f"Snippet {i}",
                similarity_score=0.9 - (i * 0.01),
            )
            for i in range(20)
        ]

        fts_service = AsyncMock()
        fts_service.find_articles.return_value = fts_results

        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results(vector_results)

        # Limit to 5 results
        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=5,
        )

        results = await hybrid_service.search("test query")

        # Should return only 5 results
        assert len(results) == 5

    async def test_hybrid_search_with_empty_fts_results(self):
        """Test hybrid search when FTS returns no results."""
        fts_service = AsyncMock()
        fts_service.find_articles.return_value = []

        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results(
            [
                FakeVectorResult(
                    url="https://example.com/vec1",
                    title="Vector Only",
                    snippet="Vector snippet",
                    similarity_score=0.9,
                )
            ]
        )

        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=10,
        )

        results = await hybrid_service.search("test query")

        # Should return vector results only
        assert len(results) == 1
        assert results[0].url == "https://example.com/vec1"

    async def test_hybrid_search_with_empty_vector_results(self):
        """Test hybrid search when vector search returns no results."""
        fts_service = AsyncMock()
        fts_service.find_articles.return_value = [
            TopicArticle(
                title="FTS Only",
                url="https://example.com/fts1",
                snippet="FTS snippet",
                source="example.com",
                published_at="2024-01-01",
            )
        ]

        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results([])

        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=10,
        )

        results = await hybrid_service.search("test query")

        # Should return FTS results only
        assert len(results) == 1
        assert results[0].url == "https://example.com/fts1"

    async def test_hybrid_search_with_empty_query(self):
        """Test hybrid search with empty query returns empty results."""
        fts_service = AsyncMock()
        vector_service = AsyncMock()

        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=10,
        )

        # Empty query
        results = await hybrid_service.search("")
        assert len(results) == 0

        # Whitespace-only query
        results = await hybrid_service.search("   ")
        assert len(results) == 0

        # Services should not be called
        fts_service.find_articles.assert_not_awaited()
        vector_service.search.assert_not_awaited()

    async def test_hybrid_search_with_query_expansion(self):
        """Test hybrid search with query expansion enabled."""
        fts_service = AsyncMock()
        fts_service.find_articles.return_value = []

        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results([])

        # Mock query expansion service
        query_expansion = MagicMock()
        query_expansion.expand_for_fts.return_value = '"ai" OR "artificial intelligence"'

        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=10,
            query_expansion=query_expansion,
        )

        await hybrid_service.search("ai")

        # Verify query expansion was used for FTS
        query_expansion.expand_for_fts.assert_called_once_with("ai")
        fts_service.find_articles.assert_awaited_once()
        # FTS should receive expanded query
        call_args = fts_service.find_articles.call_args
        assert call_args[0][0] == '"ai" OR "artificial intelligence"'

    async def test_hybrid_search_scoring_weights(self):
        """Test that FTS and vector weights affect result ranking."""
        # Create results that will have different rankings based on weights
        overlap_url = "https://example.com/overlap"

        fts_service = AsyncMock()
        fts_service.find_articles.return_value = [
            TopicArticle(
                title="Top FTS",
                url=overlap_url,
                snippet="FTS snippet",
                source="example.com",
                published_at="2024-01-01",
            ),
            TopicArticle(
                title="Second FTS",
                url="https://example.com/fts2",
                snippet="FTS snippet 2",
                source="example.com",
                published_at="2024-01-02",
            ),
        ]

        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results(
            [
                FakeVectorResult(
                    url=overlap_url,
                    title="Top FTS",
                    snippet="Vector snippet",
                    similarity_score=0.5,  # Lower vector score
                ),
            ]
        )

        # FTS-heavy weighting
        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.9,  # Heavily favor FTS
            vector_weight=0.1,
            max_results=10,
        )

        results = await hybrid_service.search("test")

        # Overlap article should rank higher due to appearing in both
        # and FTS weight being high
        assert len(results) == 2
        assert results[0].url == overlap_url  # Should be first

    async def test_hybrid_search_passes_correlation_id(self):
        """Test that correlation ID is passed to underlying services."""
        fts_service = AsyncMock()
        fts_service.find_articles.return_value = []

        vector_service = AsyncMock()
        vector_service.search.return_value = _wrap_vector_results([])

        hybrid_service = HybridSearchService(
            fts_service=fts_service,
            vector_service=vector_service,
            fts_weight=0.4,
            vector_weight=0.6,
            max_results=10,
        )

        correlation_id = "test-correlation-id-123"
        await hybrid_service.search("test query", correlation_id=correlation_id)

        # Verify correlation ID was passed to both services
        fts_call = fts_service.find_articles.call_args
        assert fts_call.kwargs.get("correlation_id") == correlation_id

        vector_call = vector_service.search.call_args
        assert vector_call.kwargs.get("correlation_id") == correlation_id

    async def test_hybrid_search_validates_weights(self):
        """Test that invalid weights raise ValueError."""
        fts_service = AsyncMock()
        vector_service = AsyncMock()

        # Invalid FTS weight (> 1.0)
        with self.assertRaises(ValueError):
            HybridSearchService(
                fts_service=fts_service,
                vector_service=vector_service,
                fts_weight=1.5,
                vector_weight=0.6,
                max_results=10,
            )

        # Invalid vector weight (< 0.0)
        with self.assertRaises(ValueError):
            HybridSearchService(
                fts_service=fts_service,
                vector_service=vector_service,
                fts_weight=0.4,
                vector_weight=-0.1,
                max_results=10,
            )

        # Invalid max_results (< 1)
        with self.assertRaises(ValueError):
            HybridSearchService(
                fts_service=fts_service,
                vector_service=vector_service,
                fts_weight=0.4,
                vector_weight=0.6,
                max_results=0,
            )


if __name__ == "__main__":
    unittest.main()

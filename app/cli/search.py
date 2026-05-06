"""CLI tool for testing search functionality."""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import TYPE_CHECKING, Any

from app.config import DatabaseConfig
from app.core.logging_utils import get_logger
from app.db.session import Database

if TYPE_CHECKING:
    from app.infrastructure.search.search_filters import SearchFilters

logging.basicConfig(
    level=logging.WARNING,  # Suppress info logs for cleaner output
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = get_logger(__name__)


def print_results(results: list[Any], mode: str, query: str) -> None:
    """Pretty print search results."""
    print(f"\n{'=' * 80}")
    print(f"Search Mode: {mode.upper()}")
    print(f"Query: '{query}'")
    print(f"Results: {len(results)}")
    print(f"{'=' * 80}\n")

    if not results:
        print("No results found.")
        return

    for idx, result in enumerate(results, 1):
        print(f"{idx}. {result.title}")
        print(f"   URL: {result.url}")

        if result.snippet:
            # Truncate long snippets
            snippet = result.snippet
            if len(snippet) > 200:
                snippet = snippet[:197] + "..."
            print(f"   {snippet}")

        if result.source:
            source_info = f"Source: {result.source}"
            if result.published_at:
                source_info += f" | Published: {result.published_at}"
            print(f"   {source_info}")

        # Show scores if available (for hybrid search results)
        if hasattr(result, "combined_score"):
            print(
                f"   Scores: Combined={result.combined_score:.3f}, "
                f"FTS={result.fts_score:.3f}, Vector={result.vector_score:.3f}"
            )

        print()


async def search_fts(db: Database, query: str, max_results: int = 10) -> list[Any]:
    """Perform full-text search."""
    from app.application.services.topic_search import LocalTopicSearchService
    from app.infrastructure.persistence.repositories.topic_search_repository import (
        SqliteTopicSearchRepositoryAdapter,
    )

    service = LocalTopicSearchService(
        repository=SqliteTopicSearchRepositoryAdapter(db), max_results=max_results
    )

    return await service.find_articles(query)


async def search_vector(
    db: Database,
    query: str,
    max_results: int = 10,
    filters: SearchFilters | None = None,
) -> list[Any]:
    """Perform vector similarity search."""
    from app.application.services.topic_search import TopicArticle
    from app.infrastructure.embedding.embedding_factory import create_embedding_service
    from app.infrastructure.persistence.repositories.embedding_repository import (
        SqliteEmbeddingRepositoryAdapter,
    )
    from app.infrastructure.persistence.repositories.topic_search_repository import (
        SqliteTopicSearchRepositoryAdapter,
    )
    from app.infrastructure.search.vector_search_service import VectorSearchService

    embedding_service = create_embedding_service()
    service = VectorSearchService(
        embedding_repository=SqliteEmbeddingRepositoryAdapter(db),
        topic_search_repository=SqliteTopicSearchRepositoryAdapter(db),
        embedding_service=embedding_service,
        max_results=max_results,
        min_similarity=0.3,
    )

    vector_results = await service.search(query, filters=filters)

    # Convert to TopicArticle format for consistent output
    return [
        TopicArticle(
            title=r.title or r.url or "Untitled",
            url=r.url or "",
            snippet=r.snippet,
            source=r.source,
            published_at=r.published_at,
        )
        for r in vector_results
    ]


async def search_hybrid(
    db: Database,
    query: str,
    max_results: int = 10,
    filters: SearchFilters | None = None,
    use_expansion: bool = True,
    use_reranking: bool = False,
) -> list[Any]:
    """Perform hybrid search (FTS + vector)."""
    from app.application.services.topic_search import LocalTopicSearchService
    from app.infrastructure.embedding.embedding_factory import create_embedding_service
    from app.infrastructure.persistence.repositories.embedding_repository import (
        SqliteEmbeddingRepositoryAdapter,
    )
    from app.infrastructure.persistence.repositories.topic_search_repository import (
        SqliteTopicSearchRepositoryAdapter,
    )
    from app.infrastructure.search.hybrid_search_service import HybridSearchService
    from app.infrastructure.search.query_expansion_service import QueryExpansionService
    from app.infrastructure.search.reranking_service import RerankingService
    from app.infrastructure.search.vector_search_service import VectorSearchService

    # Initialize FTS service
    fts_service = LocalTopicSearchService(
        repository=SqliteTopicSearchRepositoryAdapter(db), max_results=max_results
    )

    # Initialize vector service
    embedding_service = create_embedding_service()
    vector_service = VectorSearchService(
        embedding_repository=SqliteEmbeddingRepositoryAdapter(db),
        topic_search_repository=SqliteTopicSearchRepositoryAdapter(db),
        embedding_service=embedding_service,
        max_results=max_results,
        min_similarity=0.3,
    )

    # Optionally initialize query expansion
    query_expansion = QueryExpansionService() if use_expansion else None

    # Optionally initialize re-ranking
    reranking = RerankingService(top_k=max_results * 2) if use_reranking else None

    # Initialize hybrid service
    hybrid_service = HybridSearchService(
        fts_service=fts_service,
        vector_service=vector_service,
        fts_weight=0.4,
        vector_weight=0.6,
        max_results=max_results,
        query_expansion=query_expansion,
        reranking=reranking,
    )

    return await hybrid_service.search(query, filters=filters)


def _build_database(dsn: str | None) -> Database:
    config = DatabaseConfig(dsn=dsn) if dsn else DatabaseConfig()
    return Database(config=config)


async def main() -> int:
    """Main CLI entry point."""
    # Parse arguments
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m app.cli.search <query> [OPTIONS]")
        print()
        print("Search for articles using full-text, vector, or hybrid search.")
        print()
        print("Arguments:")
        print("  query                 Search query (required)")
        print()
        print("Options:")
        print("  --mode=MODE           Search mode: fts, vector, or hybrid (default: hybrid)")
        print("  --dsn=DSN             PostgreSQL DSN (default: DATABASE_URL)")
        print("  --limit=N             Maximum results to return (default: 10)")
        print("  --no-expansion        Disable query expansion for FTS (enabled by default)")
        print("  --with-reranking      Enable cross-encoder re-ranking (disabled by default)")
        print()
        print("Filters:")
        print("  --date-from=DATE      Filter by publish date >= DATE (format: YYYY-MM-DD)")
        print("  --date-to=DATE        Filter by publish date <= DATE (format: YYYY-MM-DD)")
        print("  --source=SOURCE       Filter by source (can specify multiple, comma-separated)")
        print("  --exclude-source=SRC  Exclude source (can specify multiple, comma-separated)")
        print("  --lang=LANG           Filter by language code (e.g., en, ru)")
        print()
        print("  --help, -h            Show this help message")
        print()
        print("Examples:")
        print('  python -m app.cli.search "machine learning"')
        print('  python -m app.cli.search "neural networks" --mode=vector')
        print('  python -m app.cli.search "AI" --date-from=2024-01-01 --date-to=2024-12-31')
        print('  python -m app.cli.search "python" --source=github.com,stackoverflow.com')
        print('  python -m app.cli.search "news" --exclude-source=reddit.com')
        return 0

    # Extract query and options
    import datetime as dt

    from app.infrastructure.search.search_filters import SearchFilters

    query_parts = []
    database_dsn: str | None = None
    mode = "hybrid"
    max_results = 10
    use_expansion = True  # Query expansion enabled by default
    use_reranking = False  # Re-ranking disabled by default (slower)

    # Filter parameters
    date_from = None
    date_to = None
    sources = None
    exclude_sources = None
    languages = None

    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1].lower()
            if mode not in ("fts", "vector", "hybrid"):
                print(f"Error: Invalid mode '{mode}'. Must be: fts, vector, or hybrid")
                return 1
        elif arg.startswith("--dsn="):
            database_dsn = arg.split("=", 1)[1]
        elif arg.startswith("--db="):
            print("Error: --db is no longer supported; set DATABASE_URL or use --dsn=DSN")
            return 1
        elif arg.startswith("--limit="):
            try:
                max_results = int(arg.split("=", 1)[1])
                if max_results <= 0:
                    print("Error: --limit must be a positive number")
                    return 1
            except ValueError:
                print(f"Error: Invalid limit value: {arg}")
                return 1
        elif arg == "--no-expansion":
            use_expansion = False
        elif arg == "--with-reranking":
            use_reranking = True
        elif arg.startswith("--date-from="):
            try:
                date_str = arg.split("=", 1)[1]
                date_from = dt.datetime.strptime(date_str, "%Y-%m-%d")  # noqa: DTZ007
            except ValueError:
                print("Error: Invalid date format for --date-from. Use YYYY-MM-DD")
                return 1
        elif arg.startswith("--date-to="):
            try:
                date_str = arg.split("=", 1)[1]
                date_to = dt.datetime.strptime(date_str, "%Y-%m-%d")  # noqa: DTZ007
            except ValueError:
                print("Error: Invalid date format for --date-to. Use YYYY-MM-DD")
                return 1
        elif arg.startswith("--source="):
            sources = [s.strip() for s in arg.split("=", 1)[1].split(",")]
        elif arg.startswith("--exclude-source="):
            exclude_sources = [s.strip() for s in arg.split("=", 1)[1].split(",")]
        elif arg.startswith("--lang="):
            languages = [lang.strip() for lang in arg.split("=", 1)[1].split(",")]
        elif not arg.startswith("--"):
            query_parts.append(arg)

    if not query_parts:
        print("Error: No query provided")
        return 1

    query = " ".join(query_parts)

    # Create filters if any are specified
    filters = SearchFilters(
        date_from=date_from,
        date_to=date_to,
        sources=sources,
        exclude_sources=exclude_sources,
        languages=languages,
    )

    # Perform search
    db: Database | None = None
    try:
        filter_msg = f" with filters: {filters}" if filters.has_filters() else ""
        print(f"Searching for: '{query}' using {mode} search{filter_msg}...")
        db = _build_database(database_dsn)

        if mode == "fts":
            results = await search_fts(db, query, max_results)
            # Apply filters manually for FTS
            if filters.has_filters():
                results = [r for r in results if filters.matches(r)]
        elif mode == "vector":
            results = await search_vector(db, query, max_results, filters)
        else:  # hybrid
            results = await search_hybrid(
                db, query, max_results, filters, use_expansion, use_reranking
            )

        # Display results
        print_results(results, mode, query)
        return 0

    except KeyboardInterrupt:
        print("\nSearch interrupted by user")
        return 130
    except Exception as e:
        logger.exception("Search failed")
        print(f"\nError: Search failed - {e}")
        return 1
    finally:
        if db is not None:
            await db.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

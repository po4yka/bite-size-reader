"""CLI tool to compare FTS, vector, and hybrid search results."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_all_searches(db_path: str, query: str, max_results: int = 10) -> dict:
    """Run all three search modes and return results.

    Args:
        db_path: Path to database
        query: Search query
        max_results: Maximum results per mode

    Returns:
        Dict with keys 'fts', 'vector', 'hybrid' containing search results
    """
    from app.db.database import Database
    from app.services.embedding_service import EmbeddingService
    from app.services.hybrid_search_service import HybridSearchService
    from app.services.topic_search import LocalTopicSearchService, TopicArticle
    from app.services.vector_search_service import VectorSearchService

    db = Database(path=db_path)

    # Initialize services
    embedding_service = EmbeddingService()
    fts_service = LocalTopicSearchService(db=db, max_results=max_results)
    vector_service = VectorSearchService(
        db=db,
        embedding_service=embedding_service,
        max_results=max_results,
        min_similarity=0.3,
    )
    hybrid_service = HybridSearchService(
        fts_service=fts_service,
        vector_service=vector_service,
        fts_weight=0.4,
        vector_weight=0.6,
        max_results=max_results,
    )

    # Run all searches in parallel
    print("Running searches...")
    fts_task = asyncio.create_task(fts_service.find_articles(query))
    vector_task = asyncio.create_task(vector_service.search(query))
    hybrid_task = asyncio.create_task(hybrid_service.search(query))

    fts_results, vector_results, hybrid_results = await asyncio.gather(
        fts_task, vector_task, hybrid_task
    )

    # Convert vector results to TopicArticle format
    vector_results = [
        TopicArticle(
            title=r.title or r.url or "Untitled",
            url=r.url or "",
            snippet=r.snippet,
            source=r.source,
            published_at=r.published_at,
        )
        for r in vector_results
    ]

    return {
        "fts": fts_results,
        "vector": vector_results,
        "hybrid": hybrid_results,
    }


def print_comparison(results: dict, query: str) -> None:
    """Print comparison of search results.

    Args:
        results: Dict with search results from all modes
        query: Search query
    """
    print(f"\n{'=' * 100}")
    print("SEARCH COMPARISON")
    print(f"Query: '{query}'")
    print(f"{'=' * 100}\n")

    # Print summary
    print("Results Summary:")
    print(f"  FTS (Full-Text):  {len(results['fts'])} results")
    print(f"  Vector (Semantic): {len(results['vector'])} results")
    print(f"  Hybrid (Combined): {len(results['hybrid'])} results")
    print()

    # Analyze overlap
    fts_urls = {r.url for r in results["fts"]}
    vector_urls = {r.url for r in results["vector"]}

    only_fts = fts_urls - vector_urls
    only_vector = vector_urls - fts_urls
    both = fts_urls & vector_urls

    print("Result Overlap:")
    print(f"  In both FTS & Vector: {len(both)}")
    print(f"  Only in FTS:          {len(only_fts)}")
    print(f"  Only in Vector:       {len(only_vector)}")
    print()

    # Print top results from each mode
    max_display = 5

    print(f"{'─' * 100}")
    print(f"TOP {max_display} RESULTS - FTS (FULL-TEXT SEARCH)")
    print(f"{'─' * 100}")
    print_mode_results(results["fts"][:max_display])

    print(f"{'─' * 100}")
    print(f"TOP {max_display} RESULTS - VECTOR (SEMANTIC SEARCH)")
    print(f"{'─' * 100}")
    print_mode_results(results["vector"][:max_display])

    print(f"{'─' * 100}")
    print(f"TOP {max_display} RESULTS - HYBRID (COMBINED)")
    print(f"{'─' * 100}")
    print_mode_results(results["hybrid"][:max_display])

    print(f"{'=' * 100}\n")


def print_mode_results(results: list) -> None:
    """Print results for a single search mode.

    Args:
        results: List of search results
    """
    if not results:
        print("  No results\n")
        return

    for idx, result in enumerate(results, 1):
        print(f"{idx}. {result.title}")

        # Truncate URL if too long
        url = result.url
        if len(url) > 80:
            url = url[:77] + "..."
        print(f"   {url}")

        if result.snippet:
            snippet = result.snippet
            if len(snippet) > 150:
                snippet = snippet[:147] + "..."
            print(f"   {snippet}")

        print()


async def main() -> int:
    """Main CLI entry point."""
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python -m app.cli.search_compare <query> [OPTIONS]")
        print()
        print("Compare FTS, vector, and hybrid search results side-by-side.")
        print()
        print("Arguments:")
        print("  query         Search query (required)")
        print()
        print("Options:")
        print("  --db=PATH     Database path (default: /data/app.db)")
        print("  --limit=N     Maximum results per mode (default: 10)")
        print("  --help, -h    Show this help message")
        print()
        print("Examples:")
        print('  python -m app.cli.search_compare "machine learning"')
        print('  python -m app.cli.search_compare "AI ethics" --limit=5')
        print('  python -m app.cli.search_compare "neural networks" --db=/path/to/app.db')
        return 0

    # Parse arguments
    query_parts = []
    db_path = "/data/app.db"
    max_results = 10

    for arg in sys.argv[1:]:
        if arg.startswith("--db="):
            db_path = arg.split("=", 1)[1]
        elif arg.startswith("--limit="):
            try:
                max_results = int(arg.split("=", 1)[1])
                if max_results <= 0:
                    print("Error: --limit must be a positive number")
                    return 1
            except ValueError:
                print(f"Error: Invalid limit value: {arg}")
                return 1
        elif not arg.startswith("--"):
            query_parts.append(arg)

    if not query_parts:
        print("Error: No query provided")
        return 1

    query = " ".join(query_parts)

    # Check database exists
    if db_path != ":memory:" and not Path(db_path).exists():
        print(f"Error: Database file not found: {db_path}")
        return 1

    # Run comparisons
    try:
        results = await run_all_searches(db_path, query, max_results)
        print_comparison(results, query)
        return 0

    except KeyboardInterrupt:
        print("\nComparison interrupted by user")
        return 130
    except Exception as e:
        logger.exception("Comparison failed")
        print(f"\nError: Comparison failed - {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

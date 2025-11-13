"""CLI tool to backfill embeddings for existing summaries."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from app.db.database import Database
from app.db.models import Summary, SummaryEmbedding
from app.services.embedding_service import EmbeddingService
from app.services.summary_embedding_generator import SummaryEmbeddingGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def get_summaries_without_embeddings(db: Database, limit: int | None = None) -> list[dict]:
    """Fetch summaries that don't have embeddings yet.

    Args:
        db: Database instance
        limit: Maximum number of summaries to fetch (None = all)

    Returns:
        List of dicts with keys: id, request_id, json_payload
    """

    def _query() -> list[dict]:
        # Get IDs of summaries that already have embeddings
        subquery = SummaryEmbedding.select(SummaryEmbedding.summary)

        # Query summaries without embeddings
        query = (
            Summary.select(Summary.id, Summary.request_id, Summary.json_payload)
            .where(Summary.id.not_in(subquery))
            .where(Summary.json_payload.is_null(False))
            .order_by(Summary.created_at.desc())
        )

        if limit:
            query = query.limit(limit)

        results = []
        for summary in query:
            results.append(
                {
                    "id": summary.id,
                    "request_id": summary.request_id.id if hasattr(summary.request_id, "id") else summary.request_id,
                    "json_payload": summary.json_payload,
                }
            )

        return results

    with db._database.connection_context():
        return _query()


async def backfill_embeddings(
    db_path: str = "/data/app.db",
    *,
    limit: int | None = None,
    force: bool = False,
) -> None:
    """Generate embeddings for all existing summaries.

    Args:
        db_path: Path to the database file
        limit: Maximum number of embeddings to generate (None = all)
        force: If True, regenerate all embeddings even if they exist
    """
    logger.info("Starting embedding backfill", extra={"db_path": db_path, "limit": limit, "force": force})

    # Initialize services
    db = Database(path=db_path)
    embedding_service = EmbeddingService()
    generator = SummaryEmbeddingGenerator(db=db, embedding_service=embedding_service)

    # Fetch summaries to process
    logger.info("Fetching summaries without embeddings...")
    summaries = get_summaries_without_embeddings(db, limit=limit)

    if not summaries:
        logger.info("No summaries found without embeddings")
        return

    logger.info("Found %d summaries to process", len(summaries))

    # Process summaries
    processed = 0
    failed = 0
    skipped = 0

    for idx, summary in enumerate(summaries, 1):
        summary_id = summary["id"]
        request_id = summary["request_id"]
        payload = summary["json_payload"]

        try:
            logger.info(
                "Processing %d/%d: summary_id=%d, request_id=%d",
                idx,
                len(summaries),
                summary_id,
                request_id,
            )

            success = await generator.generate_embedding_for_summary(
                summary_id=summary_id,
                payload=payload,
                force=force,
            )

            if success:
                processed += 1
            else:
                skipped += 1

            # Progress update every 10 summaries
            if idx % 10 == 0:
                logger.info(
                    "Progress: %d/%d processed, %d successful, %d skipped, %d failed",
                    idx,
                    len(summaries),
                    processed,
                    skipped,
                    failed,
                )

        except Exception:
            logger.exception("Failed to process summary %d", summary_id)
            failed += 1
            continue

    logger.info(
        "Backfill complete: %d processed, %d successful, %d skipped, %d failed",
        len(summaries),
        processed,
        skipped,
        failed,
    )


def main() -> int:
    """Main CLI entry point."""
    db_path = "/data/app.db"
    limit = None
    force = False

    # Parse arguments
    args = sys.argv[1:]
    for arg in args:
        if arg.startswith("--db="):
            db_path = arg.split("=", 1)[1]
        elif arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
            except ValueError:
                logger.error("Invalid limit value: %s", arg)
                return 1
        elif arg == "--force":
            force = True
        elif arg in ("--help", "-h"):
            print("Usage: python -m app.cli.backfill_embeddings [OPTIONS]")
            print()
            print("Options:")
            print("  --db=PATH       Database path (default: /data/app.db)")
            print("  --limit=N       Process only N summaries")
            print("  --force         Regenerate all embeddings (even if they exist)")
            print("  --help, -h      Show this help message")
            return 0

    # Check database exists (unless it's :memory:)
    if db_path != ":memory:" and not Path(db_path).exists():
        logger.error("Database file not found: %s", db_path)
        return 1

    # Run backfill
    try:
        asyncio.run(backfill_embeddings(db_path=db_path, limit=limit, force=force))
        return 0
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
        return 130
    except Exception:
        logger.exception("Backfill failed with error")
        return 1


if __name__ == "__main__":
    sys.exit(main())

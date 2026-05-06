from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.application.services.summary_embedding_generator import SummaryEmbeddingGenerator
from app.config import DatabaseConfig, load_config
from app.core.logging_utils import get_logger
from app.db.models import Request, Summary, SummaryEmbedding, model_to_dict
from app.db.session import Database
from app.infrastructure.embedding.embedding_factory import create_embedding_service
from app.infrastructure.persistence.repositories.embedding_repository import (
    SqliteEmbeddingRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)

logger = get_logger(__name__)


async def get_summaries_for_embedding_backfill(
    db: Database,
    *,
    limit: int | None = None,
    force: bool = False,
) -> list[dict]:
    """Fetch summaries that need embeddings, or all summaries when force=True."""

    async with db.session() as session:
        query = (
            select(Summary, Request)
            .join(Request, Summary.request_id == Request.id)
            .order_by(Summary.created_at.desc())
        )
        if force:
            query = query.where(Summary.json_payload.is_not(None))
        else:
            query = query.outerjoin(
                SummaryEmbedding, SummaryEmbedding.summary_id == Summary.id
            ).where(
                SummaryEmbedding.id.is_(None)
            )
        if limit:
            query = query.limit(limit)

        results = []
        rows = await session.execute(query)
        for summary, request in rows:
            item = model_to_dict(summary)
            if item:
                item["request_id"] = request.id
                results.append(item)
        return results


async def backfill_embeddings(
    database_dsn: str | None,
    limit: int | None = None,
    force: bool = False,
) -> None:
    """Run backfill process."""
    # Initialize services
    cfg = load_config(allow_stub_telegram=True)
    db = Database(config=DatabaseConfig(dsn=database_dsn) if database_dsn else DatabaseConfig())
    try:
        embedding_service = create_embedding_service(cfg.embedding)
        generator = SummaryEmbeddingGenerator(
            embedding_repository=SqliteEmbeddingRepositoryAdapter(db),
            request_repository=SqliteRequestRepositoryAdapter(db),
            summary_repository=SqliteSummaryRepositoryAdapter(db),
            embedding_service=embedding_service,
            max_token_length=cfg.embedding.max_token_length,
        )

        # Fetch summaries to process
        logger.info("Fetching summaries for embedding backfill...")
        summaries = await get_summaries_for_embedding_backfill(db, limit=limit, force=force)

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
            language = summary.get("language")

            try:
                logger.info(
                    "Processing %d/%d: summary_id=%d, request_id=%d, language=%s",
                    idx,
                    len(summaries),
                    summary_id,
                    request_id,
                    language,
                )

                success = await generator.generate_embedding_for_summary(
                    summary_id=summary_id,
                    payload=payload,
                    language=language,
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
    finally:
        await db.dispose()


def main() -> int:
    """Main CLI entry point."""
    database_dsn = None
    limit = None
    force = False

    # Parse arguments
    args = sys.argv[1:]
    for arg in args:
        if arg.startswith("--dsn="):
            database_dsn = arg.split("=", 1)[1]
        elif arg.startswith("--db="):
            logger.error("--db is no longer supported; set DATABASE_URL or use --dsn=DSN")
            return 1
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
            print("  --dsn=DSN       PostgreSQL DSN (default: DATABASE_URL)")
            print("  --limit=N       Process only N summaries")
            print("  --force         Regenerate all embeddings (even if they exist)")
            print("  --help, -h      Show this help message")
            return 0

    # Run backfill
    try:
        asyncio.run(backfill_embeddings(database_dsn=database_dsn, limit=limit, force=force))
        return 0
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
        return 130
    except Exception:
        logger.exception("Backfill failed with error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

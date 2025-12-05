"""CLI tool to sync embeddings into Chroma."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import ChromaConfig
from app.db.database import Database
from app.db.models import Summary
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.services.embedding_service import EmbeddingService
from app.services.summary_embedding_generator import SummaryEmbeddingGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _fetch_summaries(db: Database, limit: int | None) -> list[dict[str, Any]]:
    from app.db.models import Request

    def _query() -> list[dict[str, Any]]:
        query = (
            Summary.select(
                Summary.id,
                Summary.request,
                Summary.json_payload,
                Summary.lang,
                Request.lang_detected,
                Request.normalized_url,
                Request.input_url,
            )
            .join(Request)
            .order_by(Summary.created_at.desc())
        )

        if limit:
            query = query.limit(limit)

        results: list[dict[str, Any]] = []
        for row in query:
            results.append(
                {
                    "id": row.id,
                    "request_id": row.request.id if hasattr(row.request, "id") else row.request,
                    "json_payload": row.json_payload,
                    "lang": row.lang,
                    "lang_detected": row.request.lang_detected
                    if hasattr(row.request, "lang_detected")
                    else None,
                    "request": {
                        "normalized_url": row.request.normalized_url
                        if hasattr(row.request, "normalized_url")
                        else None,
                        "input_url": row.request.input_url
                        if hasattr(row.request, "input_url")
                        else None,
                    },
                }
            )
        return results

    with db._database.connection_context():
        return _query()


async def backfill_chroma_store(
    db_path: str,
    chroma_cfg: ChromaConfig,
    *,
    limit: int | None = None,
    force: bool = False,
    batch_size: int = 50,
) -> None:
    logger.info(
        "Starting Chroma backfill",
        extra={
            "db_path": db_path,
            "limit": limit,
            "force": force,
            "batch_size": batch_size,
        },
    )

    db = Database(path=db_path)
    embedding_service = EmbeddingService()
    generator = SummaryEmbeddingGenerator(db=db, embedding_service=embedding_service)
    vector_store = ChromaVectorStore(
        host=chroma_cfg.host,
        auth_token=chroma_cfg.auth_token,
        environment=chroma_cfg.environment,
        user_scope=chroma_cfg.user_scope,
    )

    summaries = _fetch_summaries(db, limit)

    if not summaries:
        logger.info("No summaries found for backfill")
        return

    pending_vectors: list[list[float]] = []
    pending_metadata: list[dict[str, Any]] = []

    processed = 0
    deleted = 0
    skipped = 0

    from app.services.metadata_builder import MetadataBuilder

    for idx, summary in enumerate(summaries, 1):
        summary_id = summary["id"]
        request_id = summary["request_id"]
        payload = summary.get("json_payload")
        language = summary.get("lang") or summary.get("lang_detected")

        logger.info(
            "Processing %d/%d: summary_id=%d request_id=%d",
            idx,
            len(summaries),
            summary_id,
            request_id,
        )

        if not payload:
            logger.info(
                "Deleting vector due to empty payload",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            vector_store.delete_by_request_id(request_id)
            deleted += 1
            continue

        existing = await db.async_get_summary_embedding(summary_id)
        if not existing or force:
            await generator.generate_embedding_for_summary(
                summary_id=summary_id,
                payload=payload,
                language=language,
                force=force,
            )
            existing = await db.async_get_summary_embedding(summary_id)

        if not existing:
            logger.warning(
                "Skipping summary without embedding",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            skipped += 1
            continue

        text, metadata = MetadataBuilder.prepare_for_upsert(
            request_id=request_id,
            summary_id=summary_id,
            payload=payload,
            language=language,
            user_scope=chroma_cfg.user_scope,
            summary_row=summary,
        )

        if not text:
            logger.info(
                "Deleting vector due to empty note text",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            vector_store.delete_by_request_id(request_id)
            deleted += 1
            continue

        embedding = embedding_service.deserialize_embedding(existing["embedding_blob"])
        vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

        pending_vectors.append(vector)
        pending_metadata.append(metadata)
        processed += 1

        if len(pending_vectors) >= batch_size:
            vector_store.upsert_notes(pending_vectors, pending_metadata)
            pending_vectors.clear()
            pending_metadata.clear()

    if pending_vectors:
        vector_store.upsert_notes(pending_vectors, pending_metadata)

    logger.info(
        "Backfill complete",
        extra={"processed": processed, "deleted": deleted, "skipped": skipped},
    )


def _load_chroma_config(
    *, host: str | None, auth_token: str | None, environment: str | None, user_scope: str | None
) -> ChromaConfig:
    base_cfg = ChromaConfig()
    return ChromaConfig(
        host=host or base_cfg.host,
        auth_token=auth_token if auth_token is not None else base_cfg.auth_token,
        environment=environment or base_cfg.environment,
        user_scope=user_scope or base_cfg.user_scope,
    )


def main() -> int:
    db_path = "/data/app.db"
    chroma_host = None
    chroma_token = None
    chroma_env = None
    chroma_scope = None
    limit = None
    force = False
    batch_size = 50

    args = sys.argv[1:]
    for arg in args:
        if arg.startswith("--db="):
            db_path = arg.split("=", 1)[1]
        elif arg.startswith("--chroma-host="):
            chroma_host = arg.split("=", 1)[1]
        elif arg.startswith("--chroma-token="):
            chroma_token = arg.split("=", 1)[1]
        elif arg.startswith("--chroma-env="):
            chroma_env = arg.split("=", 1)[1]
        elif arg.startswith("--chroma-scope="):
            chroma_scope = arg.split("=", 1)[1]
        elif arg.startswith("--limit="):
            try:
                limit = int(arg.split("=", 1)[1])
            except ValueError:
                logger.error("Invalid limit value: %s", arg)
                return 1
        elif arg == "--force":
            force = True
        elif arg.startswith("--batch-size="):
            try:
                batch_size = int(arg.split("=", 1)[1])
            except ValueError:
                logger.error("Invalid batch size: %s", arg)
                return 1
        elif arg in ("--help", "-h"):
            print("Usage: python -m app.cli.backfill_chroma_store [OPTIONS]")
            print()
            print("Options:")
            print("  --db=PATH             Database path (default: /data/app.db)")
            print("  --chroma-host=URL     Chroma host (default from environment or config)")
            print("  --chroma-token=TOKEN  Chroma auth token")
            print("  --chroma-env=NAME     Environment namespace for the collection")
            print("  --chroma-scope=NAME   User/tenant scope for the collection")
            print("  --limit=N             Process only N summaries")
            print("  --force               Regenerate embeddings even if they exist")
            print("  --batch-size=N        Number of vectors per upsert batch (default: 50)")
            print("  --help, -h            Show this help message")
            return 0

    if db_path != ":memory:" and not Path(db_path).exists():
        logger.error("Database file not found: %s", db_path)
        return 1

    try:
        chroma_cfg = _load_chroma_config(
            host=chroma_host,
            auth_token=chroma_token,
            environment=chroma_env,
            user_scope=chroma_scope,
        )
    except Exception:
        logger.exception("Failed to load Chroma configuration")
        return 1

    try:
        asyncio.run(
            backfill_chroma_store(
                db_path=db_path,
                chroma_cfg=chroma_cfg,
                limit=limit,
                force=force,
                batch_size=batch_size,
            )
        )
        return 0
    except KeyboardInterrupt:
        logger.info("Backfill interrupted by user")
        return 130
    except Exception:
        logger.exception("Backfill failed with error")
        return 1


if __name__ == "__main__":
    sys.exit(main())

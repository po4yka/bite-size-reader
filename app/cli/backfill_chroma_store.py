"""CLI tool to sync embeddings into Chroma."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from app.application.services.summary_embedding_generator import SummaryEmbeddingGenerator
from app.config import ChromaConfig, load_config
from app.core.embedding_space import resolve_embedding_space_identifier
from app.db.session import DatabaseSessionManager
from app.infrastructure.embedding.embedding_factory import create_embedding_service
from app.infrastructure.persistence.sqlite.repositories.embedding_repository import (
    SqliteEmbeddingRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.request_repository import (
    SqliteRequestRepositoryAdapter,
)
from app.infrastructure.persistence.sqlite.repositories.summary_repository import (
    SqliteSummaryRepositoryAdapter,
)
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.infrastructure.vector.metadata_builder import MetadataBuilder

logger = logging.getLogger(__name__)


def _fetch_summaries(db: DatabaseSessionManager, limit: int | None) -> list[dict[str, Any]]:
    from app.db.models import Request, Summary, model_to_dict

    def _query() -> list[dict[str, Any]]:
        query = Summary.select(Summary, Request).join(Request).order_by(Summary.created_at.desc())
        if limit:
            query = query.limit(limit)

        results = []
        for row in query:
            item = model_to_dict(row)
            if item:
                item["request_id"] = row.request.id
                item["request"] = model_to_dict(row.request)
                results.append(item)
        return results

    with db.database.connection_context():
        return _query()


async def backfill_chroma_store(
    db_path: str,
    chroma_cfg: ChromaConfig,
    *,
    limit: int | None = None,
    force: bool = False,
    batch_size: int = 50,
) -> None:
    logger.info("Initializing backfill", extra={"db_path": db_path, "limit": limit})

    app_cfg = load_config(allow_stub_telegram=True)
    db = DatabaseSessionManager(path=db_path)
    embedding_repo = SqliteEmbeddingRepositoryAdapter(db)
    embedding_service = create_embedding_service(app_cfg.embedding)
    generator = SummaryEmbeddingGenerator(
        embedding_repository=embedding_repo,
        request_repository=SqliteRequestRepositoryAdapter(db),
        summary_repository=SqliteSummaryRepositoryAdapter(db),
        embedding_service=embedding_service,
        max_token_length=app_cfg.embedding.max_token_length,
    )

    summaries = _fetch_summaries(db, limit)
    logger.info("Found %d summaries to process", len(summaries))

    vector_store = ChromaVectorStore(
        host=chroma_cfg.host,
        auth_token=chroma_cfg.auth_token,
        environment=chroma_cfg.environment,
        user_scope=chroma_cfg.user_scope,
        collection_version=chroma_cfg.collection_version,
        embedding_space=resolve_embedding_space_identifier(app_cfg.embedding),
        required=chroma_cfg.required,
        connection_timeout=chroma_cfg.connection_timeout,
    )

    processed = 0
    deleted = 0
    skipped = 0
    pending_requests: list[tuple[int, list[list[float]], list[dict[str, Any]]]] = []
    pending_vector_count = 0

    def flush_pending() -> None:
        nonlocal pending_vector_count
        for pending_request_id, request_vectors, request_metadata in pending_requests:
            vector_store.replace_request_notes(
                pending_request_id,
                request_vectors,
                request_metadata,
            )
        pending_requests.clear()
        pending_vector_count = 0

    for summary in summaries:
        summary_id = summary.get("id")
        request_id = summary.get("request_id")
        request_row = summary.get("request") if isinstance(summary.get("request"), dict) else {}
        user_id = request_row.get("user_id") if isinstance(request_row, dict) else None
        payload = summary.get("json_payload")
        language = summary.get("lang")

        if not summary_id or not request_id:
            continue

        if not payload:
            logger.info(
                "Deleting vector due to empty payload",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            vector_store.delete_by_request_id(request_id)
            deleted += 1
            continue

        existing = await embedding_repo.async_get_summary_embedding(summary_id)
        if not existing or force:
            await generator.generate_embedding_for_summary(
                summary_id=summary_id,
                payload=payload,
                language=language,
                force=force,
            )
            existing = await embedding_repo.async_get_summary_embedding(summary_id)

        if not existing:
            logger.warning("No embedding found or generated", extra={"summary_id": summary_id})
            skipped += 1
            continue

        chunk_windows = MetadataBuilder.prepare_chunk_windows_for_upsert(
            request_id=request_id,
            summary_id=summary_id,
            payload=payload,
            language=language,
            user_scope=chroma_cfg.user_scope,
            environment=chroma_cfg.environment,
            user_id=user_id,
        )

        request_vectors: list[list[float]] = []
        request_metadata: list[dict[str, Any]] = []

        if chunk_windows:
            for text, metadata in chunk_windows:
                embedding = await embedding_service.generate_embedding(
                    text, language=metadata.get("language"), task_type="document"
                )
                vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
                request_vectors.append(vector)
                request_metadata.append(metadata)
        else:
            text, metadata = MetadataBuilder.prepare_for_upsert(
                request_id=request_id,
                summary_id=summary_id,
                payload=payload,
                language=language,
                user_scope=chroma_cfg.user_scope,
                environment=chroma_cfg.environment,
                user_id=user_id,
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

            request_vectors.append(vector)
            request_metadata.append(metadata)

        if not request_vectors:
            logger.info(
                "Deleting vector due to empty generated vectors",
                extra={"request_id": request_id, "summary_id": summary_id},
            )
            vector_store.delete_by_request_id(request_id)
            deleted += 1
            continue

        pending_requests.append((request_id, request_vectors, request_metadata))
        pending_vector_count += len(request_vectors)
        processed += len(request_vectors)

        if pending_vector_count >= batch_size:
            flush_pending()

    if pending_requests:
        flush_pending()

    logger.info(
        "Backfill complete",
        extra={"processed": processed, "deleted": deleted, "skipped": skipped},
    )


def _load_chroma_config(
    *,
    host: str | None,
    auth_token: str | None,
    environment: str | None,
    user_scope: str | None,
    collection_version: str | None = None,
) -> ChromaConfig:
    base_cfg = load_config(allow_stub_telegram=True).vector_store
    return ChromaConfig(
        host=host or base_cfg.host,
        auth_token=auth_token if auth_token is not None else base_cfg.auth_token,
        environment=environment or base_cfg.environment,
        user_scope=user_scope or base_cfg.user_scope,
        collection_version=collection_version or base_cfg.collection_version,
        required=base_cfg.required,
        connection_timeout=base_cfg.connection_timeout,
    )


def main() -> int:
    db_path = "/data/app.db"
    chroma_host = None
    chroma_token = None
    chroma_env = None
    chroma_scope = None
    chroma_version = None
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
        elif arg.startswith("--chroma-version="):
            chroma_version = arg.split("=", 1)[1]
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
            print("  --chroma-env=NAME     Environment namespace for the collection")
            print("  --chroma-scope=NAME   User/tenant scope for the collection")
            print("  --chroma-version=VER  Collection version suffix (default from config)")
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
            collection_version=chroma_version,
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
    raise SystemExit(main())

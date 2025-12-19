"""Export existing summary embeddings into Chroma with rollout health checks."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.db.database import Database

from app.config import load_config
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


def upgrade(db: Database) -> None:
    """Stream existing summary embeddings into the configured Chroma collection.

    The migration reads stored embeddings, converts them into Chroma upsert payloads,
    and logs detailed health metrics (heartbeat latency, upsert timings, query
    verification) so operators can validate availability during rollout.
    """

    # Use full app config so environment overrides (e.g., CHROMA_HOST) are honored
    chroma_cfg = load_config(allow_stub_telegram=True).vector_store
    embedding_service = EmbeddingService()
    vector_store = ChromaVectorStore(
        host=chroma_cfg.host,
        auth_token=chroma_cfg.auth_token,
        environment=chroma_cfg.environment,
        user_scope=chroma_cfg.user_scope,
        collection_version=chroma_cfg.collection_version,
    )

    _log_chroma_heartbeat(vector_store)

    embeddings = list(
        _fetch_summary_embeddings(
            db,
            environment=chroma_cfg.environment,
            user_scope=chroma_cfg.user_scope,
        )
    )
    if not embeddings:
        logger.info("No summary embeddings found; nothing to migrate")
        return

    processed = 0
    skipped_empty = 0
    failed = 0
    upsert_latencies: list[float] = []

    batch_vectors: list[list[float]] = []
    batch_metadata: list[dict[str, Any]] = []
    sample_vector: list[float] | None = None
    sample_metadata: dict[str, Any] | None = None

    for entry in embeddings:
        processed += 1

        if not entry["text"]:
            skipped_empty += 1
            logger.warning(
                "Skipping embedding with empty text",
                extra={"summary_id": entry["summary_id"], "request_id": entry["request_id"]},
            )
            continue

        try:
            vector = embedding_service.deserialize_embedding(entry["embedding_blob"])
            vector_list = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        except Exception:
            failed += 1
            logger.exception(
                "Failed to deserialize embedding", extra={"summary_id": entry["summary_id"]}
            )
            continue

        # We can use MetadataBuilder.build_metadata if we reconstruct the inputs,
        # but _build_metadata was doing exactly that.
        # Let's replace _build_metadata with MetadataBuilder.build_metadata
        # but we need to adapt the input.

        # Actually, the entry dict is already flat. MetadataBuilder.build_metadata expects payload/summary_row.
        # Maybe it's better to keep the migration script simple as it is a one-off,
        # OR update it to use the new standard.

        # Given this is a migration script, it might be better to leave it alone if it works,
        # BUT the task is to refactor.
        # Let's see if we can make it cleaner.

        metadata = {
            "request_id": entry.get("request_id"),
            "summary_id": entry.get("summary_id"),
            "language": entry.get("language"),
            "url": entry.get("url"),
            "title": entry.get("title"),
            "source": entry.get("source"),
            "published_at": entry.get("published_at"),
            "text": entry.get("text"),
            "user_scope": chroma_cfg.user_scope,
            "environment": chroma_cfg.environment,
        }
        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}

        batch_vectors.append(vector_list)
        batch_metadata.append(metadata)

        if sample_vector is None:
            sample_vector = vector_list
            sample_metadata = metadata

        if len(batch_vectors) >= 50:
            latency_ms = _upsert_with_latency(vector_store, batch_vectors, batch_metadata)
            upsert_latencies.append(latency_ms)
            batch_vectors.clear()
            batch_metadata.clear()

    if batch_vectors:
        latency_ms = _upsert_with_latency(vector_store, batch_vectors, batch_metadata)
        upsert_latencies.append(latency_ms)

    _log_upsert_metrics(processed, skipped_empty, failed, upsert_latencies)

    if sample_vector and sample_metadata:
        _log_query_probe(vector_store, sample_vector, sample_metadata)


def downgrade(db: Database) -> None:
    """No-op rollback placeholder.

    Chroma writes cannot be rolled back automatically. Operators can manually
    delete collections if a rollback is required.
    """

    logger.info("Chroma ingestion rollback is a no-op; manual cleanup may be required")


def _fetch_summary_embeddings(
    db: Database, *, environment: str, user_scope: str
) -> Iterable[dict[str, Any]]:
    from app.db.models import Request, Summary, SummaryEmbedding
    from app.services.metadata_builder import MetadataBuilder

    with db._database.atomic():  # Use atomic transaction for proper management
        query = (
            SummaryEmbedding.select(SummaryEmbedding, Summary, Request).join(Summary).join(Request)
        )

        for row in query:
            payload = row.summary.json_payload or {}

            # Use MetadataBuilder to generate text and metadata
            # We need to adapt the inputs slightly

            summary_row = {
                "request_id": row.summary.request.id,
                "id": row.summary.id,
                "lang": row.language or row.summary.lang or row.summary.request.lang_detected,
                "request": {
                    "normalized_url": row.summary.request.normalized_url,
                    "input_url": row.summary.request.input_url,
                },
            }

            # We don't have user_scope here, but prepare_for_upsert needs it.
            # However, the migration script passes user_scope later.
            # We just need the text and the basic metadata.

            # Actually, let's just use MetadataBuilder.prepare_for_upsert and ignore the user_scope in the result
            # if we want, or pass a dummy one and override it.

            text, metadata = MetadataBuilder.prepare_for_upsert(
                request_id=row.summary.request.id,
                summary_id=row.summary.id,
                payload=payload,
                language=summary_row["lang"],
                user_scope=user_scope,
                environment=environment,
                summary_row=summary_row,
            )

            yield {
                "request_id": row.summary.request.id,
                "summary_id": row.summary.id,
                "language": summary_row["lang"],
                "embedding_blob": row.embedding_blob,
                "url": metadata.get("url"),
                "title": metadata.get("title"),
                "source": metadata.get("source"),
                "published_at": metadata.get("published_at"),
                "text": text,
                "tags": metadata.get(
                    "tags"
                ),  # MetadataBuilder doesn't extract tags explicitly in build_metadata yet?
                # Wait, build_note_text extracts tags into metadata.
            }


def _upsert_with_latency(
    vector_store: ChromaVectorStore, vectors: list[list[float]], metadatas: list[dict[str, Any]]
) -> float:
    start = time.perf_counter()
    vector_store.upsert_notes(vectors, metadatas)
    latency_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "chroma_upsert_batch",
        extra={"batch_size": len(vectors), "latency_ms": round(latency_ms, 2)},
    )
    return latency_ms


def _log_upsert_metrics(
    processed: int, skipped_empty: int, failed: int, upsert_latencies: list[float]
) -> None:
    avg_latency = sum(upsert_latencies) / len(upsert_latencies) if upsert_latencies else 0.0
    max_latency = max(upsert_latencies) if upsert_latencies else 0.0
    logger.info(
        "chroma_migration_summary",
        extra={
            "processed_rows": processed,
            "skipped_empty": skipped_empty,
            "deserialize_failures": failed,
            "batches": len(upsert_latencies),
            "upsert_latency_avg_ms": round(avg_latency, 2),
            "upsert_latency_max_ms": round(max_latency, 2),
        },
    )


def _log_query_probe(
    vector_store: ChromaVectorStore, vector: list[float], metadata: dict[str, Any]
) -> None:
    try:
        start = time.perf_counter()
        response = vector_store.query(vector, {"request_id": metadata.get("request_id")}, 1)
        latency_ms = (time.perf_counter() - start) * 1000
        ids = response.get("ids") or []
        returned = ids[0] if ids and isinstance(ids, list) else []
        success = bool(returned)
        logger.info(
            "chroma_query_probe",
            extra={
                "latency_ms": round(latency_ms, 2),
                "request_id": metadata.get("request_id"),
                "success": success,
            },
        )
    except Exception:
        logger.exception(
            "chroma_query_probe_failed", extra={"request_id": metadata.get("request_id")}
        )


def _log_chroma_heartbeat(vector_store: ChromaVectorStore) -> None:
    client = getattr(vector_store, "_client", None)
    if client is None:
        logger.warning("chroma_client_missing", extra={"collection": "unknown"})
        return

    try:
        start = time.perf_counter()
        heartbeat = client.heartbeat()
        latency_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "chroma_heartbeat",
            extra={"heartbeat": heartbeat, "latency_ms": round(latency_ms, 2)},
        )
    except Exception:
        logger.exception("chroma_heartbeat_failed")
        raise

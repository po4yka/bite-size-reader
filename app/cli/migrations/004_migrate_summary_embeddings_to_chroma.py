"""Export existing summary embeddings into Chroma with rollout health checks."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.db.database import Database

from app.config import ChromaConfig
from app.infrastructure.vector.chroma_store import ChromaVectorStore
from app.services.embedding_service import EmbeddingService
from app.services.note_text_builder import _extract_tags, build_note_text

logger = logging.getLogger(__name__)


def upgrade(db: Database) -> None:
    """Stream existing summary embeddings into the configured Chroma collection.

    The migration reads stored embeddings, converts them into Chroma upsert payloads,
    and logs detailed health metrics (heartbeat latency, upsert timings, query
    verification) so operators can validate availability during rollout.
    """

    chroma_cfg = ChromaConfig()
    embedding_service = EmbeddingService()
    vector_store = ChromaVectorStore(
        host=chroma_cfg.host,
        auth_token=chroma_cfg.auth_token,
        environment=chroma_cfg.environment,
        user_scope=chroma_cfg.user_scope,
    )

    _log_chroma_heartbeat(vector_store)

    embeddings = list(_fetch_summary_embeddings(db))
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

        metadata = _build_metadata(entry, chroma_cfg.user_scope)

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


def _fetch_summary_embeddings(db: Database) -> Iterable[dict[str, Any]]:
    from app.db.models import Request, Summary, SummaryEmbedding

    with db._database.atomic():  # Use atomic transaction for proper management
        query = (
            SummaryEmbedding.select(SummaryEmbedding, Summary, Request).join(Summary).join(Request)
        )

        for row in query:
            payload = row.summary.json_payload or {}
            metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}

            url = (
                metadata.get("canonical_url")
                or metadata.get("url")
                or row.summary.request.normalized_url
                or row.summary.request.input_url
            )
            title = metadata.get("title") or payload.get("title")
            source = metadata.get("domain") or metadata.get("source")
            published_at = metadata.get("published_at") or metadata.get("published")

            snippet = (
                payload.get("summary_250")
                or payload.get("tldr")
                or payload.get("summary_1000")
                or metadata.get("summary")
            )
            if snippet and len(snippet) > 300:
                snippet = str(snippet)[:297] + "..."

            language = row.language or row.summary.lang or row.summary.request.lang_detected

            note_text = build_note_text(
                payload,
                request_id=row.summary.request.id,
                summary_id=row.summary.id,
                language=language,
                user_note=_extract_user_note(payload),
            )

            yield {
                "request_id": row.summary.request.id,
                "summary_id": row.summary.id,
                "language": language,
                "embedding_blob": row.embedding_blob,
                "url": url,
                "title": title,
                "source": source,
                "published_at": published_at,
                "snippet": snippet,
                "text": note_text.text,
                "tags": _extract_tags(payload, metadata),
            }


def _extract_user_note(payload: dict[str, Any] | None) -> str | None:
    payload = payload or {}
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}

    for key in ("user_note", "note", "notes"):
        candidate = payload.get(key) or metadata.get(key)
        if candidate:
            return str(candidate)
    return None


def _build_metadata(entry: dict[str, Any], user_scope: str) -> dict[str, Any]:
    metadata = {
        "request_id": entry.get("request_id"),
        "summary_id": entry.get("summary_id"),
        "language": entry.get("language"),
        "url": entry.get("url"),
        "title": entry.get("title"),
        "source": entry.get("source"),
        "published_at": entry.get("published_at"),
        "snippet": entry.get("snippet"),
        "text": entry.get("text"),
        "tags": entry.get("tags"),
        "user_scope": user_scope,
    }
    return {k: v for k, v in metadata.items() if v is not None}


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

"""Backfill existing summary embeddings into the configured Chroma collection.

Requires Chroma to be reachable. If Chroma is not configured, logs a warning
and exits cleanly (the migration is recorded as applied so it is not re-run).

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-04
"""

from __future__ import annotations

import logging
import time
from typing import Any

from alembic import op
from sqlalchemy import text

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

logger = logging.getLogger(__name__)


def upgrade() -> None:
    conn = op.get_bind()
    try:
        from app.config import load_config
        from app.core.embedding_space import resolve_embedding_space_identifier
        from app.infrastructure.embedding.embedding_factory import create_embedding_service
        from app.infrastructure.vector.chroma_store import ChromaVectorStore
        from app.infrastructure.vector.metadata_builder import MetadataBuilder
    except ImportError as exc:
        logger.warning("chroma_migration_skipped_missing_deps: %s", exc)
        return

    try:
        app_cfg = load_config(allow_stub_telegram=True)
        chroma_cfg = app_cfg.vector_store
        embedding_service = create_embedding_service()
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
    except Exception as exc:
        logger.warning("chroma_migration_skipped_config_error: %s", exc)
        return

    rows = conn.execute(text("""
        SELECT se.embedding_blob, se.language,
               s.id AS summary_id, s.json_payload, s.lang,
               r.id AS request_id, r.normalized_url, r.input_url,
               r.user_id, r.lang_detected
        FROM summary_embeddings se
        JOIN summaries s ON se.summary_id = s.id
        JOIN requests r ON s.request_id = r.id
    """)).fetchall()

    if not rows:
        logger.info("chroma_migration_no_embeddings")
        return

    processed = skipped = failed = 0
    batch_vectors: list[list[float]] = []
    batch_metadata: list[dict[str, Any]] = []
    upsert_latencies: list[float] = []

    for row in rows:
        processed += 1
        blob, language, summary_id, json_payload, lang, request_id, norm_url, input_url, user_id, lang_detected = row
        effective_lang = language or lang or lang_detected
        payload = json_payload or {}
        if isinstance(payload, str):
            import json
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        summary_row = {
            "request_id": request_id,
            "id": summary_id,
            "lang": effective_lang,
            "request": {"normalized_url": norm_url, "input_url": input_url, "user_id": user_id},
        }
        try:
            text_val, metadata = MetadataBuilder.prepare_for_upsert(
                request_id=request_id,
                summary_id=summary_id,
                payload=payload,
                language=effective_lang,
                user_scope=chroma_cfg.user_scope,
                environment=chroma_cfg.environment,
                user_id=user_id,
                summary_row=summary_row,
            )
        except Exception as exc:
            logger.warning("chroma_migration_metadata_error: %s", exc)
            skipped += 1
            continue
        if not text_val:
            skipped += 1
            continue
        try:
            vector = embedding_service.deserialize_embedding(blob)
            vector_list = vector.tolist() if hasattr(vector, "tolist") else list(vector)
        except Exception:
            failed += 1
            continue
        batch_vectors.append(vector_list)
        batch_metadata.append(metadata)
        if len(batch_vectors) >= 50:
            t0 = time.perf_counter()
            vector_store.upsert_notes(batch_vectors, batch_metadata)
            upsert_latencies.append((time.perf_counter() - t0) * 1000)
            batch_vectors.clear()
            batch_metadata.clear()

    if batch_vectors:
        t0 = time.perf_counter()
        vector_store.upsert_notes(batch_vectors, batch_metadata)
        upsert_latencies.append((time.perf_counter() - t0) * 1000)

    logger.info(
        "chroma_migration_complete processed=%d skipped=%d failed=%d batches=%d",
        processed, skipped, failed, len(upsert_latencies),
    )


def downgrade() -> None:
    logger.info("chroma_migration_downgrade_noop: manual Chroma cleanup required")

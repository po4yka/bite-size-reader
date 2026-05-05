"""One-shot CLI to migrate vector data from ChromaDB to Qdrant.

Communicates with Chroma over its HTTP REST API (no Python chromadb package required),
and writes to Qdrant via ``QdrantVectorStore``.

Strategies
----------
auto   (default) - probe Chroma; use export if the source collection has data,
                   otherwise fall back to reembed.
export            - dump vectors from Chroma HTTP API and upsert into Qdrant.
reembed           - read summaries from SQLite, regenerate embeddings, upsert into Qdrant.

Usage
-----
    python -m app.cli.migrate_vector_store \\
        --chroma-host http://chroma:8000 \\
        --qdrant-url  http://qdrant:6333 \\
        [--strategy auto|export|reembed] \\
        [--batch-size 50] \\
        [--dry-run]
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from app.config import QdrantConfig, load_config
from app.core.embedding_space import resolve_embedding_space_identifier
from app.core.logging_utils import get_logger
from app.infrastructure.vector.qdrant_store import QdrantVectorStore

logger = get_logger(__name__)

_CHROMA_DEFAULT = "http://localhost:8000"
_QDRANT_DEFAULT = "http://localhost:6333"
_UUID_NAMESPACE = uuid.NAMESPACE_OID


def _str_to_uuid(s: str) -> str:
    return str(uuid.uuid5(_UUID_NAMESPACE, s))


# ---------------------------------------------------------------------------
# Chroma HTTP client helpers
# ---------------------------------------------------------------------------


async def _chroma_list_collections(base_url: str, auth_token: str | None) -> list[dict[str, Any]]:
    import httpx

    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        resp = await client.get("/api/v1/collections", headers=headers)
        resp.raise_for_status()
        return resp.json()


async def _chroma_get_collection(
    base_url: str, name: str, auth_token: str | None
) -> dict[str, Any] | None:
    import httpx

    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        resp = await client.get(f"/api/v1/collections/{name}", headers=headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()


async def _chroma_get_batch(
    base_url: str,
    collection_id: str,
    auth_token: str | None,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    import httpx

    headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
    body = {
        "ids": None,
        "include": ["embeddings", "metadatas", "documents"],
        "limit": limit,
        "offset": offset,
    }
    async with httpx.AsyncClient(base_url=base_url, timeout=60) as client:
        resp = await client.post(
            f"/api/v1/collections/{collection_id}/get",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Collection name resolution
# ---------------------------------------------------------------------------


def _resolve_collection_name(
    environment: str,
    user_scope: str,
    collection_version: str,
    embedding_space: str | None,
) -> str:
    """Reconstruct the Chroma collection name the bot used."""
    parts = ["notes", environment, user_scope, collection_version]
    if embedding_space:
        parts.append(embedding_space)
    return "_".join(parts)


# ---------------------------------------------------------------------------
# Export path: Chroma HTTP → Qdrant
# ---------------------------------------------------------------------------


async def _export_from_chroma(
    chroma_host: str,
    chroma_auth: str | None,
    vector_store: QdrantVectorStore,
    collection_name: str,
    batch_size: int,
    dry_run: bool,
) -> int:
    collection = await _chroma_get_collection(chroma_host, collection_name, chroma_auth)
    if not collection:
        logger.warning("chroma_collection_not_found", extra={"name": collection_name})
        return 0

    collection_id = collection.get("id") or collection_name
    total = 0
    offset = 0

    while True:
        batch = await _chroma_get_batch(chroma_host, collection_id, chroma_auth, offset, batch_size)
        ids: list[str] = batch.get("ids") or []
        embeddings: list[list[float]] = batch.get("embeddings") or []
        metadatas: list[dict[str, Any]] = batch.get("metadatas") or []

        if not ids:
            break

        if not dry_run:
            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=_str_to_uuid(chroma_id),
                    vector=emb,
                    payload=meta or {},
                )
                for chroma_id, emb, meta in zip(ids, embeddings, metadatas, strict=True)
                if emb
            ]
            if points:
                vector_store._client.upsert(
                    collection_name=vector_store.collection_name,
                    points=points,
                )

        total += len(ids)
        logger.info(
            "vector_migration_batch",
            extra={
                "strategy": "export",
                "source": "chroma",
                "dest": "qdrant",
                "count": len(ids),
                "total_so_far": total,
            },
        )
        offset += batch_size

    return total


# ---------------------------------------------------------------------------
# Reembed path: SQLite → Qdrant
# ---------------------------------------------------------------------------


async def _reembed_from_sqlite(
    db_path: str,
    vector_store: QdrantVectorStore,
    qdrant_cfg: QdrantConfig,
    app_cfg: Any,
    batch_size: int,
    dry_run: bool,
) -> int:
    from app.cli.backfill_vector_store import backfill_vector_store

    await backfill_vector_store(
        db_path,
        qdrant_cfg,
        batch_size=batch_size,
        dry_run=dry_run,
    )
    return vector_store.count() if not dry_run else 0


# ---------------------------------------------------------------------------
# Verification probe
# ---------------------------------------------------------------------------


async def _verify_migration(
    db_path: str,
    vector_store: QdrantVectorStore,
    app_cfg: Any,
    sample: int = 3,
) -> bool:
    from app.db.session import DatabaseSessionManager
    from app.infrastructure.embedding.embedding_factory import create_embedding_service
    from app.infrastructure.persistence.sqlite.orm_exports import Request, Summary

    db = DatabaseSessionManager(path=db_path)
    embedding_service = create_embedding_service(app_cfg.embedding)

    def _sample_ids() -> list[tuple[int, int, str]]:
        with db.database.connection_context():
            rows = (
                Summary.select(Summary.id, Summary.json_payload, Request.id)
                .join(Request)
                .where(Summary.is_deleted == False)  # noqa: E712
                .limit(sample)
            )
            return [
                (row.id, row.request.id, str(row.json_payload.get("summary_250", "test")))
                for row in rows
                if row.json_payload
            ]

    samples = _sample_ids()
    if not samples:
        logger.warning("vector_migration_verification_no_samples")
        return True

    ok_count = 0
    for _summary_id, request_id, text in samples:
        emb = await embedding_service.generate_embedding(text, language="en", task_type="query")
        vector = emb.tolist() if hasattr(emb, "tolist") else list(emb)

        result = vector_store.query(vector, None, 10)
        found_ids = {int(h.metadata.get("request_id", -1)) for h in result.hits}
        if request_id in found_ids:
            ok_count += 1

    passed = ok_count == len(samples)
    logger.info(
        "vector_migration_verification",
        extra={"ok": passed, "checked": len(samples), "matched": ok_count},
    )
    return passed


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def migrate(
    *,
    chroma_host: str,
    chroma_auth: str | None,
    qdrant_url: str,
    qdrant_api_key: str | None,
    strategy: str,
    db_path: str,
    batch_size: int,
    dry_run: bool,
) -> int:
    app_cfg = load_config(allow_stub_telegram=True)
    qdrant_cfg = app_cfg.vector_store

    embedding_space = resolve_embedding_space_identifier(app_cfg.embedding)
    collection_name = _resolve_collection_name(
        environment=qdrant_cfg.environment,
        user_scope=qdrant_cfg.user_scope,
        collection_version=qdrant_cfg.collection_version,
        embedding_space=embedding_space,
    )

    resolved_qdrant_cfg = QdrantConfig(
        url=qdrant_url or qdrant_cfg.url,
        api_key=qdrant_api_key if qdrant_api_key is not None else qdrant_cfg.api_key,
        environment=qdrant_cfg.environment,
        user_scope=qdrant_cfg.user_scope,
        collection_version=qdrant_cfg.collection_version,
        required=True,
        connection_timeout=qdrant_cfg.connection_timeout,
    )

    vector_store = QdrantVectorStore(
        url=resolved_qdrant_cfg.url,
        api_key=resolved_qdrant_cfg.api_key,
        environment=resolved_qdrant_cfg.environment,
        user_scope=resolved_qdrant_cfg.user_scope,
        collection_version=resolved_qdrant_cfg.collection_version,
        embedding_space=embedding_space,
        required=True,
        connection_timeout=resolved_qdrant_cfg.connection_timeout,
    )

    if not vector_store.available:
        logger.error("vector_migration_qdrant_unavailable", extra={"url": resolved_qdrant_cfg.url})
        return 1

    logger.info(
        "vector_migration_start",
        extra={
            "chroma_host": chroma_host,
            "qdrant_url": resolved_qdrant_cfg.url,
            "strategy": strategy,
            "collection_name": collection_name,
            "dry_run": dry_run,
        },
    )

    effective_strategy = strategy
    if strategy == "auto":
        try:
            collections = await _chroma_list_collections(chroma_host, chroma_auth)
            collection_names = [c.get("name", "") for c in collections]
            if collection_name in collection_names:
                collection_info = await _chroma_get_collection(
                    chroma_host, collection_name, chroma_auth
                )
                chroma_count = collection_info.get("metadata", {}).get("count", 0) if collection_info else 0
                effective_strategy = "export" if chroma_count > 0 else "reembed"
            else:
                effective_strategy = "reembed"
        except Exception:
            logger.warning("vector_migration_chroma_probe_failed", exc_info=True)
            effective_strategy = "reembed"
        logger.info(
            "vector_migration_strategy_resolved",
            extra={"strategy": effective_strategy},
        )

    if effective_strategy == "export":
        count = await _export_from_chroma(
            chroma_host, chroma_auth, vector_store, collection_name, batch_size, dry_run
        )
        logger.info("vector_migration_export_done", extra={"points_migrated": count})
    else:
        count = await _reembed_from_sqlite(
            db_path, vector_store, resolved_qdrant_cfg, app_cfg, batch_size, dry_run
        )
        logger.info("vector_migration_reembed_done", extra={"points_written": count})

    if not dry_run:
        ok = await _verify_migration(db_path, vector_store, app_cfg)
        if not ok:
            logger.error("vector_migration_verification_failed")
            return 1
        logger.info("vector_migration_verification_passed")

    vector_store.close()
    return 0


def main() -> int:
    chroma_host = _CHROMA_DEFAULT
    chroma_auth = None
    qdrant_url = _QDRANT_DEFAULT
    qdrant_api_key = None
    strategy = "auto"
    db_path = "/data/ratatoskr.db"
    batch_size = 50
    dry_run = False

    args = sys.argv[1:]
    for arg in args:
        if arg.startswith("--chroma-host="):
            chroma_host = arg.split("=", 1)[1]
        elif arg.startswith("--chroma-auth="):
            chroma_auth = arg.split("=", 1)[1]
        elif arg.startswith("--qdrant-url="):
            qdrant_url = arg.split("=", 1)[1]
        elif arg.startswith("--qdrant-api-key="):
            qdrant_api_key = arg.split("=", 1)[1]
        elif arg.startswith("--strategy="):
            strategy = arg.split("=", 1)[1]
            if strategy not in ("auto", "export", "reembed"):
                print(f"Invalid strategy: {strategy!r}. Must be auto, export, or reembed.")
                return 1
        elif arg.startswith("--db="):
            db_path = arg.split("=", 1)[1]
        elif arg.startswith("--batch-size="):
            try:
                batch_size = int(arg.split("=", 1)[1])
            except ValueError:
                print(f"Invalid batch-size: {arg}")
                return 1
        elif arg == "--dry-run":
            dry_run = True
        elif arg in ("--help", "-h"):
            print("Usage: python -m app.cli.migrate_vector_store [OPTIONS]")
            print()
            print("Options:")
            print(f"  --chroma-host=URL    ChromaDB base URL (default: {_CHROMA_DEFAULT})")
            print("  --chroma-auth=TOKEN  ChromaDB bearer token (optional)")
            print(f"  --qdrant-url=URL     Qdrant base URL (default: {_QDRANT_DEFAULT})")
            print("  --qdrant-api-key=KEY Qdrant API key (optional)")
            print("  --strategy=STRATEGY  Migration strategy: auto|export|reembed (default: auto)")
            print("  --db=PATH            SQLite database path (default: /data/ratatoskr.db)")
            print("  --batch-size=N       Points per batch (default: 50)")
            print("  --dry-run            Simulate without writing to Qdrant")
            print("  --help, -h           Show this help message")
            return 0

    try:
        return asyncio.run(
            migrate(
                chroma_host=chroma_host,
                chroma_auth=chroma_auth,
                qdrant_url=qdrant_url,
                qdrant_api_key=qdrant_api_key,
                strategy=strategy,
                db_path=db_path,
                batch_size=batch_size,
                dry_run=dry_run,
            )
        )
    except KeyboardInterrupt:
        logger.info("Migration interrupted by user")
        return 130
    except Exception:
        logger.exception("Migration failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

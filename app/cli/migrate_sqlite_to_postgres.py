"""One-shot ETL: copy every row from a SQLite file into a PostgreSQL database.

Usage
-----
    python -m app.cli.migrate_sqlite_to_postgres \\
        --source-sqlite /data/ratatoskr.db \\
        --target-postgres postgresql+asyncpg://...

The script:
1. Opens the source SQLite in read-only mode via the frozen Peewee snapshot.
2. Runs Alembic migrations on the target Postgres.
3. Iterates models in FK-safe order (peewee.sort_models), skipping TopicSearchIndex.
4. Streams rows in batches and upserts via INSERT ... ON CONFLICT DO NOTHING.
5. Resets Postgres sequences for all integer-PK tables.
6. Rebuilds the topic_search_index via TopicSearchIndexManager.
7. Validates row counts and samples FK cardinalities.
8. Prints a final report and exits 0 on success, non-zero on any mismatch.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import os
import time
from typing import Any

import peewee
import sqlalchemy
from sqlalchemy import BigInteger, Integer, LargeBinary, func, select, text
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

import app.db.models as sa_models
from app.cli._legacy_peewee_models import ALL_MODELS, TopicSearchIndex as LegacyTopicSearchIndex
from app.cli._legacy_peewee_models._base import database_proxy
from app.config.database import DatabaseConfig
from app.core.logging_utils import get_logger
from app.db.alembic_runner import upgrade_to_head
from app.db.json_utils import normalize_legacy_json_value
from app.db.session import Database
from app.db.topic_search_manager import TopicSearchIndexManager

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chunked(iterable: Any, size: int):
    """Yield successive chunks of up to *size* items from *iterable*."""
    it = iter(iterable)
    while True:
        chunk = list(itertools.islice(it, size))
        if not chunk:
            break
        yield chunk


def _is_json_column(col: Any) -> bool:
    """Return True when the column stores JSON/JSONB."""
    return isinstance(col.type, (PG_JSONB, sqlalchemy.JSON))


def _is_bytes_column(col: Any) -> bool:
    """Return True when the column stores raw binary data."""
    return isinstance(col.type, LargeBinary)


def _pk_columns(sa_model: type[Any]) -> list[Any]:
    """Return list of primary-key columns for a SQLAlchemy model."""
    return list(sa_model.__table__.primary_key.columns)


def _legacy_table_exists(legacy_model: type[Any]) -> bool:
    """Return True when the legacy model's table is present in the source DB.

    Production sources have every table, but partial-schema sources
    (test fixtures, ad-hoc backups) may not. Callers should skip absent
    tables with a warning rather than crashing the whole migration.
    """
    db = legacy_model._meta.database
    table_name = legacy_model._meta.table_name
    try:
        return bool(db.table_exists(table_name))
    except peewee.OperationalError:
        return False


def _resolve_sa_model(legacy_model: type[Any]) -> type[Any] | None:
    """Look up the SQLAlchemy model whose class name matches the legacy model."""
    return getattr(sa_models, legacy_model.__name__, None)


def _legacy_row_to_dict(
    legacy_model: type[Any],
    row: peewee.Model,
    sa_model: type[Any],
) -> dict[str, Any]:
    """Convert a Peewee row to a plain dict with SA-column-compatible keys.

    - Uses field.column_name (not field attr name) to handle FK ``_id`` suffix.
    - Intersects with SA column names so extra legacy columns are dropped.
    - Applies normalize_legacy_json_value to all JSONB columns.
    - Passes LargeBinary columns through unchanged.
    """
    sa_col_names: set[str] = {c.name for c in sa_model.__table__.columns}
    sa_col_map: dict[str, Any] = {
        c.name: c for c in sa_model.__table__.columns
    }

    result: dict[str, Any] = {}
    for field_name, field in legacy_model._meta.fields.items():
        col_name = field.column_name  # e.g. "user" -> "user_id" for FKs
        if col_name not in sa_col_names:
            continue

        raw_value = getattr(row, field_name)
        # FK fields return model instances in Peewee; extract the PK integer.
        if isinstance(raw_value, peewee.Model):
            raw_value = raw_value.get_id()

        sa_col = sa_col_map[col_name]

        if _is_json_column(sa_col):
            normalized, was_legacy, reason = normalize_legacy_json_value(raw_value)
            if was_legacy and reason:
                logger.debug(
                    "json_normalization_applied",
                    extra={
                        "model": sa_model.__tablename__,
                        "column": col_name,
                        "reason": reason,
                    },
                )
            result[col_name] = normalized
        elif _is_bytes_column(sa_col):
            # Pass bytes through unchanged (e.g. SummaryEmbedding.embedding_blob).
            result[col_name] = raw_value
        else:
            result[col_name] = raw_value

    return result


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------


async def _migrate_model(
    legacy_model: type[Any],
    sa_model: type[Any],
    database: Database,
    batch_size: int,
    dry_run: bool,
) -> tuple[int, int]:
    """Migrate all rows for one model pair.

    Returns (source_count, migrated_count).
    """
    pk_cols = _pk_columns(sa_model)
    pk_col_names = [c.name for c in pk_cols]
    table_name = sa_model.__tablename__

    if not _legacy_table_exists(legacy_model):
        logger.warning(
            "model_skip_missing_source_table",
            extra={"model": table_name, "legacy_table": legacy_model._meta.table_name},
        )
        return 0, 0

    source_count: int = legacy_model.select().count()
    if source_count == 0:
        logger.info(
            "model_skip_empty",
            extra={"model": table_name, "source_count": 0},
        )
        return 0, 0

    migrated = 0
    for chunk in _chunked(legacy_model.select().iterator(), batch_size):
        payload = [_legacy_row_to_dict(legacy_model, row, sa_model) for row in chunk]

        if dry_run:
            migrated += len(payload)
            continue

        stmt = (
            pg_insert(sa_model)
            .values(payload)
            .on_conflict_do_nothing(index_elements=pk_col_names)
        )
        async with database.transaction() as session:
            await session.execute(stmt)

        migrated += len(payload)
        logger.info(
            "batch_inserted",
            extra={
                "model": table_name,
                "chunk_size": len(payload),
                "cumulative": migrated,
            },
        )

    return source_count, migrated


async def _reset_sequences(database: Database, dry_run: bool) -> dict[str, int]:
    """Reset Postgres SERIAL sequences to max(pk) for all single-integer-PK tables."""
    results: dict[str, int] = {}

    for sa_model in sa_models.ALL_MODELS:
        pk_cols = _pk_columns(sa_model)
        if len(pk_cols) != 1:
            continue
        pk_col = pk_cols[0]
        if not isinstance(pk_col.type, Integer | BigInteger):
            continue

        table_name = sa_model.__tablename__
        col_name = pk_col.name

        if dry_run:
            results[f"{table_name}.{col_name}"] = -1
            continue

        sql = text(
            f"SELECT setval("
            f"pg_get_serial_sequence(:tbl, :col),"
            f" COALESCE((SELECT MAX({col_name}) FROM {table_name}), 1))"
        )
        try:
            async with database.engine.begin() as conn:
                row = await conn.execute(sql, {"tbl": table_name, "col": col_name})
                value = row.scalar()
                if value is not None:
                    results[f"{table_name}.{col_name}"] = int(value)
        except Exception:
            logger.debug(
                "sequence_reset_skipped",
                extra={"table": table_name, "col": col_name},
            )

    return results


async def _count_target(database: Database, sa_model: type[Any]) -> int:
    """Count rows in the target Postgres table."""
    async with database.session() as session:
        result = await session.scalar(select(func.count()).select_from(sa_model))
        return int(result or 0)


async def _validate(
    sorted_models: list[type[Any]],
    sa_model_map: dict[str, type[Any]],
    database: Database,
) -> tuple[dict[str, tuple[int, int]], list[str]]:
    """Compare source vs target row counts; return (counts_map, mismatch_list)."""
    counts: dict[str, tuple[int, int]] = {}
    mismatches: list[str] = []

    for legacy_model in sorted_models:
        sa_model = sa_model_map.get(legacy_model.__name__)
        if sa_model is None:
            continue
        if not _legacy_table_exists(legacy_model):
            continue
        src = legacy_model.select().count()
        tgt = await _count_target(database, sa_model)
        counts[legacy_model.__name__] = (src, tgt)
        if src != tgt:
            mismatches.append(f"{legacy_model.__name__}: source={src} target={tgt}")

    return counts, mismatches


async def _sample_fk_cardinalities(database: Database) -> list[str]:
    """Sample 10 random Request IDs and check child counts in source vs target."""
    issues: list[str] = []

    async with database.session() as session:
        # Pick up to 10 request IDs from target
        rows = await session.execute(
            select(sa_models.Request.id).order_by(func.random()).limit(10)
        )
        request_ids = [r[0] for r in rows]

    if not request_ids:
        return issues

    # For each child, compare legacy vs target counts per request_id
    from app.cli._legacy_peewee_models._core import (
        Summary as LegacySummary,
        CrawlResult as LegacyCrawlResult,
        LLMCall as LegacyLLMCall,
        TelegramMessage as LegacyTelegramMessage,
    )
    legacy_pairs = [
        (LegacySummary, sa_models.Summary, "request_id"),
        (LegacyCrawlResult, sa_models.CrawlResult, "request_id"),
        (LegacyLLMCall, sa_models.LLMCall, "request_id"),
        (LegacyTelegramMessage, sa_models.TelegramMessage, "request_id"),
    ]

    for legacy_child, sa_child, fk_col in legacy_pairs:
        if not _legacy_table_exists(legacy_child):
            continue
        for rid in request_ids:
            legacy_count = legacy_child.select().where(
                getattr(legacy_child, fk_col) == rid
            ).count()
            async with database.session() as session:
                tgt_count = await session.scalar(
                    select(func.count()).select_from(sa_child).where(
                        getattr(sa_child, fk_col) == rid
                    )
                )
            tgt_count = int(tgt_count or 0)
            if legacy_count != tgt_count:
                issues.append(
                    f"{sa_child.__tablename__}[request_id={rid}]: "
                    f"source={legacy_count} target={tgt_count}"
                )

    return issues


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


async def run_migration(
    source_sqlite: str,
    target_postgres: str,
    dry_run: bool,
    batch_size: int,
    skip_fts_rebuild: bool,
) -> int:
    """Run the full migration pipeline. Returns exit code."""
    start_time = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Open source SQLite in read-only mode
    # ------------------------------------------------------------------
    logger.info("opening_source_sqlite", extra={"path": source_sqlite})
    legacy_db = peewee.SqliteDatabase(source_sqlite, pragmas={"query_only": 1})
    database_proxy.initialize(legacy_db)

    # ------------------------------------------------------------------
    # 2. Open target Postgres
    # ------------------------------------------------------------------
    logger.info("opening_target_postgres", extra={"dsn": target_postgres[:30] + "..."})
    db_config = DatabaseConfig.model_validate({"DATABASE_URL": target_postgres})
    database = Database(config=db_config)
    try:
        await database.healthcheck()
    except Exception as exc:
        logger.error("target_postgres_healthcheck_failed", extra={"error": str(exc)})
        await database.dispose()
        return 1

    try:
        # ------------------------------------------------------------------
        # 3. Run Alembic migrations (sync — run in executor)
        # ------------------------------------------------------------------
        if not dry_run:
            logger.info("running_alembic_migrations")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, upgrade_to_head, target_postgres)
            logger.info("alembic_migrations_complete")

        # ------------------------------------------------------------------
        # 4. Iterate models in FK-safe order
        # ------------------------------------------------------------------
        sorted_models = peewee.sort_models(list(ALL_MODELS))

        skipped_models: list[str] = []
        sa_model_map: dict[str, type[Any]] = {}

        total_source = 0
        total_migrated = 0

        for legacy_model in sorted_models:
            # Always skip TopicSearchIndex — rebuilt from scratch in step 6.
            if legacy_model is LegacyTopicSearchIndex:
                logger.info(
                    "model_skipped_fts",
                    extra={"model": legacy_model.__name__},
                )
                continue

            sa_model = _resolve_sa_model(legacy_model)
            if sa_model is None:
                msg = (
                    f"WARNING: legacy model {legacy_model.__name__!r} has no "
                    f"SQLAlchemy counterpart — skipping"
                )
                logger.warning(msg)
                skipped_models.append(legacy_model.__name__)
                continue

            sa_model_map[legacy_model.__name__] = sa_model

            logger.info(
                "migrating_model",
                extra={"model": legacy_model.__name__},
            )
            try:
                src_count, mig_count = await _migrate_model(
                    legacy_model, sa_model, database, batch_size, dry_run
                )
                total_source += src_count
                total_migrated += mig_count
            except Exception:
                logger.exception(
                    "model_migration_failed",
                    extra={"model": legacy_model.__name__},
                )
                return 2

        # ------------------------------------------------------------------
        # 5. Sequence reset
        # ------------------------------------------------------------------
        logger.info("resetting_sequences")
        seq_values = await _reset_sequences(database, dry_run)

        # ------------------------------------------------------------------
        # 6. Topic search rebuild
        # ------------------------------------------------------------------
        fts_row_count = 0
        if not skip_fts_rebuild and not dry_run:
            logger.info("rebuilding_topic_search_index")
            manager = TopicSearchIndexManager(database, logger)
            await manager.ensure_index()
            # Count the resulting rows
            fts_row_count = await _count_target(database, sa_models.TopicSearchIndex)
            logger.info(
                "topic_search_index_rebuilt",
                extra={"rows": fts_row_count},
            )

        # ------------------------------------------------------------------
        # 7. Validation
        # ------------------------------------------------------------------
        exit_code = 0
        if not dry_run:
            logger.info("validating_row_counts")
            counts, mismatches = await _validate(sorted_models, sa_model_map, database)
            fk_issues = await _sample_fk_cardinalities(database)
            if mismatches or fk_issues:
                exit_code = 3
        else:
            counts = {}
            mismatches = []
            fk_issues = []

        # ------------------------------------------------------------------
        # 8. Final report
        # ------------------------------------------------------------------
        elapsed = time.monotonic() - start_time
        print("\n" + "=" * 60)
        print("MIGRATION REPORT")
        print("=" * 60)
        print(f"Mode       : {'DRY RUN' if dry_run else 'LIVE'}")
        print(f"Source     : {source_sqlite}")
        print(f"Target     : {target_postgres[:50]}...")
        print(f"Batch size : {batch_size}")
        print(f"Elapsed    : {elapsed:.1f}s")
        print()
        print(f"Total source rows : {total_source}")
        print(f"Total migrated    : {total_migrated}")
        print()

        if counts:
            print("Per-table counts (source / target):")
            for name, (src, tgt) in counts.items():
                flag = " *** MISMATCH" if src != tgt else ""
                print(f"  {name:<40} {src:>8} / {tgt:>8}{flag}")
            print()

        if mismatches:
            print("COUNT MISMATCHES:")
            for m in mismatches:
                print(f"  {m}")
            print()

        if fk_issues:
            print("FK CARDINALITY ISSUES:")
            for issue in fk_issues:
                print(f"  {issue}")
            print()

        if skipped_models:
            print("Skipped models (no SA counterpart):")
            for name in skipped_models:
                print(f"  {name}")
            print()

        if seq_values and not dry_run:
            print("Sequence resets (sample):")
            for k, v in list(seq_values.items())[:10]:
                print(f"  {k}: {v}")
            print()

        if not skip_fts_rebuild and not dry_run:
            print(f"FTS rows rebuilt : {fts_row_count}")
            print()

        if exit_code == 0:
            print("STATUS: SUCCESS")
        else:
            print(f"STATUS: FAILED (exit code {exit_code})")

        print("=" * 60)
        return exit_code

    finally:
        await database.dispose()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.migrate_sqlite_to_postgres",
        description="One-shot SQLite-to-Postgres ETL for Ratatoskr.",
    )
    parser.add_argument(
        "--source-sqlite",
        default=os.environ.get("DB_PATH", "/data/ratatoskr.db"),
        metavar="PATH",
        help="Path to source SQLite file (default: $DB_PATH or /data/ratatoskr.db)",
    )
    parser.add_argument(
        "--target-postgres",
        default=os.environ.get("DATABASE_URL"),
        metavar="DSN",
        help="Target PostgreSQL asyncpg DSN (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan and counts without writing to target",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        metavar="N",
        help="Rows per INSERT batch (default: 500)",
    )
    parser.add_argument(
        "--skip-fts-rebuild",
        action="store_true",
        help="Skip topic_search_index rebuild after load",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    if not args.target_postgres:
        parser.error(
            "--target-postgres is required (or set DATABASE_URL environment variable)"
        )

    if not args.source_sqlite:
        parser.error("--source-sqlite is required (or set DB_PATH environment variable)")

    try:
        return asyncio.run(
            run_migration(
                source_sqlite=args.source_sqlite,
                target_postgres=args.target_postgres,
                dry_run=args.dry_run,
                batch_size=args.batch_size,
                skip_fts_rebuild=args.skip_fts_rebuild,
            )
        )
    except KeyboardInterrupt:
        logger.info("migration_interrupted_by_user")
        return 130
    except Exception:
        logger.exception("migration_failed_with_unhandled_error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

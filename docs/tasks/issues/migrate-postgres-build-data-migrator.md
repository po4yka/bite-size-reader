---
title: Build SQLite to Postgres data migrator
status: review
area: db
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-write-pi-runbook
  - migrate-postgres-execute-pi-cutover
blocked_by:
  - migrate-postgres-port-models-features
  - migrate-postgres-port-topic-search-model
  - migrate-postgres-baseline-alembic-revision
  - migrate-postgres-update-alembic-env
  - migrate-postgres-port-runtime-services
  - migrate-postgres-add-compose-service
  - migrate-postgres-port-application-call-sites
created: 2026-05-06
updated: 2026-05-07
---

- [ ] #task Build SQLite to Postgres data migrator #repo/ratatoskr #area/db #status/review 🔺

## Objective

Ship `python -m app.cli.migrate_sqlite_to_postgres` — a one-shot ETL that copies
every row from a source SQLite file (read via the frozen Peewee snapshot) into a
target Postgres database via SQLAlchemy 2.0 `AsyncSession`, with full
validation.

## Context

Why dual-stack inside a single CLI:

- Read side **must** stay on Peewee — that's the only way to read the existing
  SQLite file; SQLAlchemy can talk to SQLite, but the legacy Peewee field
  metadata (especially `playhouse.sqlite_ext.JSONField` storage quirks and
  `_coerce_json_columns` semantics) is the reference for correct row decoding.
- Write side is SQLAlchemy 2.0 / asyncpg — the same target the live application
  uses, so no behavioural drift.
- Frozen Peewee snapshot lives in `app/cli/_legacy_peewee_models/` (created
  during M1/M2). The CLI is the **only** importer of that package. After L1
  (peewee removal), the package is deleted along with `peewee` itself.

Pipeline:

1. CLI args: `--source-sqlite <path>` (default: legacy `DB_PATH`),
   `--target-postgres <dsn>` (default: `DATABASE_URL`), `--dry-run`,
   `--batch-size 500`, `--skip-fts-rebuild`.
2. Open both connections: legacy Peewee on the SQLite file (read-only mode,
   `pragmas={"query_only": 1}`), and the F3 `Database` on Postgres.
3. Run `alembic upgrade head` against Postgres (so the schema exists).
4. For each model in `peewee.sort_models(LEGACY_ALL_MODELS)`:
   - `SELECT *` from source in chunks of `batch_size` via
     `LegacyModel.select().iterator()`,
   - normalise each row: apply `normalize_legacy_json_value` to JSON columns;
     decode `BlobField` bytes for `SummaryEmbedding.embedding_blob`,
   - assemble dicts matching the new SQLAlchemy model's column names,
   - `await session.execute(insert(NewModel).values(rows).on_conflict_do_nothing(
     index_elements=[primary_key_col]))`,
   - emit a structured progress log every chunk.
5. After load: for every table with an autoincrement PK,
   `await session.execute(text(
   "SELECT setval(pg_get_serial_sequence('<table>', 'id'),
   COALESCE((SELECT MAX(id) FROM <table>), 1))"))`.
6. Rebuild `topic_search_index` by calling
   `TopicSearchIndexManager.ensure_index()` (the new SQLAlchemy version) — the
   computed `body_tsv` column populates automatically from the regular
   columns.
7. Validation: per-table source/target row count comparison; for each
   parent/child pair (Request → Summary, Request → CrawlResult,
   Request → LLMCall, etc.) sample 10 random parent IDs and assert child
   cardinalities match.
8. Final report: `pre/post counts, mismatches, sequence values, fts row count,
   elapsed seconds`. Exit non-zero on any mismatch.

## Acceptance criteria

- [ ] `app/cli/migrate_sqlite_to_postgres.py` implemented per the pipeline above.
- [ ] Reads via `app.cli._legacy_peewee_models`, writes via the new SQLAlchemy
      `Database` and `AsyncSession`.
- [ ] `--dry-run` reports row counts, FK ordering, and the planned chunk count
      without writing.
- [ ] On a development copy of the Pi DB (498 MB), full migration completes on
      a developer laptop in < 15 minutes.
- [ ] Validation report shows zero mismatches against the source.
- [ ] After migration, `python -m app.cli.summary --url <known-good-url>` runs
      end to end against the new Postgres DB and produces a summary
      indistinguishable from the SQLite run.
- [ ] Topic search returns ≥ 50% overlap with SQLite results across the T3
      regression query set.
- [ ] Unit tests for the per-row coercion and per-model insert ordering, run on
      a tiny synthetic DB in CI.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  Model Fields, Alembic, and the Telethon Session Caveat. The temporary legacy
  Peewee snapshot is allowed only for this CLI and cleanup phase L1.
- FK ordering: `peewee.sort_models()` over `LEGACY_ALL_MODELS` gives
  topological order. If conflicts persist, run the load inside
  `await connection.execute(text("SET session_replication_role = 'replica'"))`
  and reset to `'origin'` at the end. Use sparingly — masks real issues.
- Memory: the source side uses `iterator()` for server-side cursor; the
  target side flushes every batch — total memory stays well under 256 MiB
  even for the 498 MB DB.
- Bytes round-trip: `SummaryEmbedding.embedding_blob` is `bytes` in Peewee,
  must arrive as `bytes` in SQLAlchemy `LargeBinary` / `BYTEA`. Pin with a
  unit test.

## Progress

- 2026-05-07: shipped `app/cli/migrate_sqlite_to_postgres.py` (575
  lines) implementing the spec pipeline end-to-end — opens the legacy
  SQLite via `peewee.SqliteDatabase(query_only=1)`, runs Alembic
  upgrade, iterates `peewee.sort_models(ALL_MODELS)` (skipping
  `TopicSearchIndex`), maps each row through `_legacy_row_to_dict`
  (handles FK column-name suffix via `field.column_name`, normalises
  JSONB columns through `normalize_legacy_json_value`, passes
  `LargeBinary` columns through unchanged), upserts via
  `postgresql.insert(...).on_conflict_do_nothing(index_elements=…)`,
  resets every autoincrement sequence, calls
  `TopicSearchIndexManager.ensure_index()`, and validates per-table
  counts and sampled FK cardinalities.
- All 51 legacy models (52 minus the deliberately-skipped
  `TopicSearchIndex`) resolve to a SQLAlchemy counterpart by class
  name — zero unmapped models.
- Tests: `tests/cli/test_migrate_sqlite_to_postgres.py` ships 11 tests
  (9 unit pass without Postgres covering JSON coercion, FK ordering
  spot-checks, dry-run plan generation; 2 skip cleanly when
  `TEST_DATABASE_URL` is unset for the bytes round-trip and
  end-to-end runs).
- Status flipped to `review` on 2026-05-07. Open verification gates:
  - end-to-end run against the live 498 MB Pi-DB snapshot (currently
    only synthetic in-memory SQLite has been exercised),
  - `_sample_fk_cardinalities` uses `func.random()` — fine for smoke
    validation but NOT a deterministic CI assertion; replace if T3 CI
    matrix wants determinism here,
  - possible `memoryview → bytes` guard if the Pi SQLite returns
    `embedding_blob` as a `memoryview` rather than `bytes`,
  - stylistic: `DatabaseConfig.model_validate({"DATABASE_URL": dsn})`
    is more cumbersome than the sibling CLIs' `DatabaseConfig(dsn=…)`
    form — could be aligned in a follow-up.

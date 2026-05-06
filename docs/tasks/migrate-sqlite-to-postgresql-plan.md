# SQLite → PostgreSQL + Peewee → SQLAlchemy 2.0 Migration Plan

> **Status:** active. Decisions D1 (dedicated `ratatoskr-postgres` container) and D2
> (port to SQLAlchemy 2.0 simultaneously) confirmed on 2026-05-06.
> **Source of truth for tasks:** `docs/tasks/issues/migrate-postgres-*.md`.
> **Created:** 2026-05-06 · **Owner:** Nikita Pochaev

## Goal

Replace two stacks at once:

1. **Storage**: SQLite (`/data/ratatoskr.db`, 498 MB on the Pi) → PostgreSQL 16 in a
   dedicated `ratatoskr-postgres` container.
2. **ORM**: Peewee + `playhouse.sqlite_ext` → SQLAlchemy 2.0 typed declarative +
   asyncpg, with native `async`/`await` sessions and no application-level write lock.

End state: `ratatoskr-bot` and `ratatoskr-mobile-api` on `raspi` run against
PostgreSQL via SQLAlchemy 2.0 `AsyncSession`, with every pre-cutover row preserved
and the correlation-id chain (request → crawl_result / llm_call / summary) intact.

Out of scope: Qdrant, ChromaDB, Redis. `SummaryEmbedding.embedding_blob` stays in
PostgreSQL as `bytea`.

## Why

- **Concurrency ceiling**: SQLite + WAL serialises writers; today the bot
  compensates with an application-level `AsyncRWLock`
  (`app/db/runtime/operation_executor.py`) and retry on `database is locked`. Both
  disappear under Postgres MVCC + SQLAlchemy async sessions.
- **Async correctness**: every Peewee call is currently wrapped in
  `asyncio.to_thread(...)`. Native `asyncpg` + SQLAlchemy `AsyncSession` eliminates
  the thread-bounce and gives proper async cancellation semantics.
- **Type safety**: SQLAlchemy 2.0 `Mapped[T]` columns are statically typed, which
  pairs well with the existing `mypy --python_version=3.13` setup.
- **Operational headroom**: a real DB server with `pg_dump` + WAL beats a 498 MB
  single file on SD-card-backed storage.
- **Tooling**: Alembic autogenerate, `EXPLAIN ANALYZE`, JSONB path indexes, partial
  indexes, generated `tsvector` columns — all unlock UX work that's awkward today.

## Current vs target architecture

### Current

```
ratatoskr-bot ─┐
               ├──► /data/ratatoskr.db  (498 MB, WAL)
mobile-api ────┘                         · Peewee SqliteDatabase
                                         · playhouse.sqlite_ext.JSONField
                                         · FTS5Model TopicSearchIndex
                                         · asyncio.to_thread() around every op
                                         · AsyncRWLock serialising writes
```

### Target

```
ratatoskr-bot ─┐
               ├──► postgres:16-alpine (ratatoskr-postgres container)
mobile-api ────┘                         · SQLAlchemy 2.0 typed declarative models
                                         · asyncpg driver, async_sessionmaker
                                         · sqlalchemy.dialects.postgresql.JSONB
                                         · TSVECTOR + GIN topic_search_index
                                         · Native async — no to_thread, no RWLock
                                         · Alembic autogenerate from declarative metadata
```

## Strategy

### 1. Single-leap port, not phased

D2 picked the bigger lift deliberately. Doing the storage swap and ORM port in two
back-to-back releases would mean:

- Rewriting `app/db/session.py` once for Postgres+Peewee, then again for
  Postgres+SQLAlchemy.
- Rewriting every call site once for `playhouse.postgres_ext`, then again for
  SQLAlchemy.
- Carrying two copies of every model temporarily.

A single port avoids that duplication. The cutover is one window, not two.

### 2. Models are typed, async, and declarative

```python
# Illustrative — not the literal final form.
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Request(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    correlation_id: Mapped[str | None] = mapped_column(String, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    dedupe_hash: Mapped[str | None] = mapped_column(String, unique=True)
    error_context_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    # … 49 models in total

    summaries: Mapped[list["Summary"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )
```

Every call site changes shape:

```python
# Old (Peewee, blocking, wrapped in to_thread):
summary = Summary.get_or_none(Summary.request == request_id)

# New (SQLAlchemy 2.0, native async):
async with session_maker() as session:
    summary = await session.scalar(
        select(Summary).where(Summary.request_id == request_id)
    )
```

### 3. Async session lifecycle

Two injection patterns:

- **FastAPI** (`app/api/`): per-request `AsyncSession` via a `Depends(get_session)`
  generator that opens a transaction, yields, commits/rolls back on exit.
- **Telegram bot + background tasks** (`app/adapters/telegram/`,
  `app/agents/`, `app/cli/`): per-operation
  `async with session_maker() as session, session.begin(): …` blocks. No
  contextvars; no global session.

Connection pool: `create_async_engine(dsn, pool_size=8, max_overflow=4,
pool_pre_ping=True, pool_recycle=900)`. Conservative for a Pi.

### 4. FTS replacement

`TopicSearchIndex` becomes a regular SQLAlchemy model with:

- `body_tsv: Mapped[TSVECTOR] = mapped_column(
    TSVECTOR,
    Computed("to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(body,''))",
             persisted=True),
  )`
- A `GIN` index via `Index("ix_topic_search_body_tsv", "body_tsv",
  postgresql_using="gin")`.
- Queries: `select(Request.id).where(text("body_tsv @@ websearch_to_tsquery('simple',
  :q)")).order_by(text("ts_rank_cd(body_tsv, websearch_to_tsquery('simple', :q))
  DESC"))`.

The public surface (`find_request_ids`, `refresh_index`, `ensure_index`) keeps the
same signatures but the underlying class is now a SQLAlchemy model, not an
`FTS5Model` subclass.

### 5. Data migration: standalone Peewee read → SQLAlchemy write

The migrator (`python -m app.cli.migrate_sqlite_to_postgres`) imports both stacks
side by side:

- **Read side**: a *frozen* Peewee model snapshot (copied into
  `app/cli/_legacy_peewee_models.py`) that mirrors today's `_models_*.py`. This
  dependency is contained — it never runs except during the migrator and is deleted
  in cleanup phase L1.
- **Write side**: the new SQLAlchemy `AsyncSession`.

Pipeline:

1. Open SQLite via legacy Peewee in read-only mode.
2. Run Alembic on Postgres so the schema exists at head.
3. For each table in topological FK order: stream rows from Peewee
   (`Model.select().iterator()`) → coerce JSON columns →
   `await session.execute(insert(...).on_conflict_do_nothing())` in batches of 500.
4. After all tables: reset every sequence
   (`SELECT setval(pg_get_serial_sequence('<t>', 'id'), MAX(id))`).
5. Rebuild `topic_search_index` by calling
   `TopicSearchIndexManager.ensure_index()`.
6. Validate row counts and parent/child cardinalities.

### 6. Cutover model: maintenance window, no dual-write

Single-user bot. Dual-write doubles bug surface for no benefit. Plan: stop bot →
snapshot SQLite → run migrator → flip env → restart. SQLite file kept read-only for
7-day rollback.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| 49-model SQLAlchemy port introduces silent bugs | Staged port in M-phase tasks, model-by-model fixture parity tests in T3 (insert via SQLAlchemy → read back equal to a fixture). |
| `asyncio.to_thread` removal breaks an unaudited sync caller | F1 audit explicitly catalogs every Peewee call site; R-phase tasks port them in batches with passing tests after each batch. |
| `AsyncRWLock` removal exposes a previously masked race | The lock today only serialises against SQLite's single-writer; on Postgres, the same workload runs naturally under MVCC. T3 includes a concurrency stress test (parallel summary creation for the same URL — exercises the dedupe_hash unique index). |
| FastAPI sessions leak on cancellation | `Depends(get_session)` uses a `try/finally` that always closes; covered by an HTTP test that cancels mid-request. |
| Alembic autogenerate emits a destructive diff | Initial baseline is hand-reviewed and committed as `0001_baseline_sqlalchemy.py`; subsequent diffs gated by code review. |
| `pg_dump` not in image | Backup runs on the host (cron) or in a dedicated `postgres:16-alpine` exec, not from the bot image. Decided per O4 implementation. |
| Telethon's own SQLite session DB is *not* migrating | Documented in F1 audit as an explicit non-target — Telethon does not support Postgres sessions. |

## Rollback

1. Stop ratatoskr/mobile-api.
2. Restore `data/ratatoskr.db.pre-pg-<date>`.
3. Roll the application image back to the last pre-port tag (`git tag -l
   pre-sqlalchemy-port` — created in C1 as a prerequisite).
4. Restart compose with `DATABASE_URL` unset, `DB_PATH` regaining effect via the
   pre-port image.

Note: because SQLAlchemy and Peewee are mutually exclusive in code, rollback
requires the *image*, not just env. C1 must produce both images in CI before the
window opens.

## Phased task list

Critical path: `D1, D2 → F1 → F2 → F3 → M1..M4 → R1..R3 → O2..O5 → T1..T3 → C1 → C2
→ L1, L2`.

### Phase D — Decisions (done)

- ✅ **D1** `migrate-postgres-decide-deployment-topology` — dedicated `ratatoskr-postgres` container.
- ✅ **D2** `migrate-postgres-decide-orm-strategy` — port to SQLAlchemy 2.0 simultaneously.

### Phase F — Foundation

- **F1** `migrate-postgres-audit-sqlite-surface` — catalog every Peewee + SQLite
  call site to drive the M and R phase worklists.
- **F2** `migrate-postgres-add-driver-and-pooling-deps` — add `sqlalchemy>=2.0`,
  `asyncpg`, `greenlet`, `alembic`, remove `peewee` only at L2.
- **F3** `migrate-postgres-introduce-database-factory` — replace
  `DatabaseSessionManager` with a SQLAlchemy `AsyncEngine` +
  `async_sessionmaker[AsyncSession]` factory; expose `get_session()` for both
  FastAPI `Depends` and bot/CLI usage.

### Phase M — Model layer port (new)

- **M1** `migrate-postgres-port-models-core` — port the eleven core models
  (`User`, `Chat`, `Request`, `TelegramMessage`, `CrawlResult`, `LLMCall`,
  `Summary`, `UserInteraction`, `AuditLog`, `SummaryEmbedding`, `RefreshToken`).
- **M2** `migrate-postgres-port-models-features` — port the feature models
  (digest, RSS, rules, signal, batch, collections, aggregation, attachment,
  audio, video, user-content) — the remaining ~38 classes.
- **M3** `migrate-postgres-port-topic-search-model` — port `TopicSearchIndex` to
  TSVECTOR + Computed + GIN; replace `find_request_ids` implementation.
- **M4** `migrate-postgres-baseline-alembic-revision` — autogenerate the
  `0001_baseline_sqlalchemy.py` revision against an empty Postgres, hand-review,
  commit. Archive (do not delete) the legacy SQLite-flavoured revisions under
  `app/db/alembic/versions/_legacy_sqlite/`.

### Phase R — Repository / call-site port (new)

- **R1** `migrate-postgres-port-runtime-services` — rewrite `app/db/runtime/{
  bootstrap,backup,inspection,maintenance,operation_executor}.py` against
  `AsyncSession` and `AsyncEngine`. Remove `AsyncRWLock` and
  `asyncio.to_thread` wrappers. `operation_executor.py` collapses to retry-on-
  `serialization_failure` only.
- **R2** `migrate-postgres-port-persistence-repositories` — port repositories
  under `app/infrastructure/persistence/` to async SQLAlchemy.
- **R3** `migrate-postgres-port-application-call-sites` — port direct ORM calls
  in `app/api/`, `app/adapters/`, `app/agents/`, `app/cli/` (excluding the
  legacy migrator), `app/application/`, `app/domain/services/`. Migrate by
  module, with module-scoped tests passing between each batch.

### Phase O — Adjacent ports (renumbered after model port)

- **O2** `migrate-postgres-port-raw-sql-helpers` — every direct
  `database.execute_sql(...)` and `sqlite3.connect(...)` outside the legacy
  migrator, ported to `text()` / `await connection.execute(text(...))` or
  removed.
- **O5** `migrate-postgres-update-alembic-env` — `app/db/alembic/env.py` becomes
  SQLAlchemy-native (autogenerate enabled, asyncpg-aware via
  `async_engine_from_config`); the legacy `alembic_runner.py` shrinks to
  `command.upgrade(cfg, "head")`.

### Phase T — Tooling

- **T1** `migrate-postgres-add-compose-service` — `postgres:16-alpine` service
  + healthcheck + named volume + Pi overlay confirmation.
- **T2** `migrate-postgres-build-data-migrator` — `python -m
  app.cli.migrate_sqlite_to_postgres` reading via frozen Peewee snapshot,
  writing via SQLAlchemy `AsyncSession`. Includes JSON coercion, sequence
  reset, FTS rebuild, and validation report.
- **T3** `migrate-postgres-add-test-fixtures-and-ci` — async test fixtures
  (`pytest-asyncio`, `async_sessionmaker` per-test schema), Postgres CI matrix
  job, FTS regression query set.

### Phase C — Cutover

- **C1** `migrate-postgres-write-pi-runbook` — step-by-step runbook in
  `docs/runbooks/pi-postgres-cutover.md`. Includes building both pre-port and
  post-port images and tagging them so rollback is image-revert + env-revert.
- **C2** `migrate-postgres-execute-pi-cutover` — owner-driven execution on
  `raspi`.

### Phase L — Cleanup

- **L1** `migrate-postgres-remove-peewee` — remove `peewee` from `pyproject.toml`,
  delete `app/cli/_legacy_peewee_models.py`, delete the
  `_legacy_sqlite` archived Alembic revisions, after the deployment has run on
  Postgres for ≥ 30 days.
- **L2** `migrate-postgres-update-docs` — `CLAUDE.md`, `docs/SPEC.md`,
  `README.md`, architecture diagram, environment-variable reference, and
  `.cursor/rules/*.mdc` lines that mention SQLite or Peewee.

## Open questions for the owner

These do **not** block start-of-work, but should be answered during the relevant
task:

1. **Postgres version**: 16 (recommended; default in T1).
2. **Cutover window**: any time, or specific quiet hours? (C2 scheduling.)
3. **Backups**: nightly `pg_dump` to `/home/po4yka/ratatoskr/backups/` retained 14
   days — acceptable, or wire WAL archiving to an external location?
4. **`SummaryEmbedding.embedding_blob`** stays in PG as `bytea`, or drop it now
   that Qdrant carries the vector? (Default: keep — out of scope.)

## Acceptance criteria for the migration as a whole

- [ ] `ratatoskr-bot` and `ratatoskr-mobile-api` on `raspi` run against PostgreSQL
      via SQLAlchemy 2.0 + asyncpg.
- [ ] `peewee` is no longer imported anywhere in `app/`, `clients/`, or `tests/`.
- [ ] `AsyncRWLock` is deleted; no `asyncio.to_thread(...)` remains in
      `app/db/`.
- [ ] Every row from the pre-cutover SQLite snapshot is queryable in Postgres
      (table-by-table count parity; sampled parent/child cardinalities match).
- [ ] Topic search FTS regression set returns ≥ 50% overlap with SQLite results
      (T3 fixture).
- [ ] Alembic head is the SQLAlchemy-autogenerated baseline; no SQLite-flavoured
      revisions execute.
- [ ] No `database is locked` events in 24h post-cutover.
- [ ] Rollback path verified once on the dev laptop using image-revert.

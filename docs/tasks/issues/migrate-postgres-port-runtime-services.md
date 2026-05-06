---
title: Port runtime services to AsyncSession
status: review
area: db
priority: high
owner: Nikita Pochaev
blocks:
  - migrate-postgres-port-persistence-repositories
  - migrate-postgres-build-data-migrator
blocked_by:
  - migrate-postgres-port-models-core
  - migrate-postgres-introduce-database-factory
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Port runtime services to AsyncSession #repo/ratatoskr #area/db #status/review ⏫

## Objective

Rewrite the four runtime services in `app/db/runtime/` against SQLAlchemy 2.0
`AsyncEngine` / `AsyncSession`, deleting the `AsyncRWLock` and the
`asyncio.to_thread` wrappers that exist only to compensate for SQLite.

## Context

In-scope files and their target shapes:

1. `bootstrap.py` — `migrate()` now just runs `alembic upgrade head`. The
   Peewee `create_tables(...)` step is gone (Alembic owns DDL post-M4).
2. `operation_executor.py` — collapses to `with_serialization_retry` decorator
   (already added in F3) plus a thin `async_execute(callable, session)` helper
   for legacy callers during R3 migration. `AsyncRWLock` is deleted.
3. `backup.py` — `create_backup_copy(dest)` shells out to `pg_dump --format=custom
   --file=<dest> <DSN>`. The DSN comes from the `Database` instance. Returns the
   path. `pg_dump` runs on the host (cron) or via `docker compose exec postgres
   pg_dump …`; not from the bot image. Decide which during implementation.
4. `inspection.py` — `check_integrity()` returns `(True, "ok")` if a trivial
   `SELECT 1` succeeds and `pg_stat_database.datname=<db>` shows zero
   `xact_rollback` deltas in the last hour; otherwise `(False, reason)`.
   `get_database_overview()` runs per-table `SELECT COUNT(*)` via
   `await session.scalar(select(func.count()).select_from(Model))`.
5. `maintenance.py` — `run_startup_maintenance()` becomes a no-op with an info
   log. `VACUUM ANALYZE` on demand is a separate manual command, not startup
   work.

`app/db/rw_lock.py` is deleted.

## Acceptance criteria

- [x] `app/db/runtime/{bootstrap,backup,inspection,maintenance}.py` rewritten
      against SQLAlchemy. Public method names preserved so callers in `app/api/
      services/system_maintenance_service.py` and similar do not change.
- [x] `app/db/runtime/operation_executor.py` reduced to retry helper only.
- [x] `app/db/rw_lock.py` deleted; no remaining imports anywhere.
- [x] `bootstrap.migrate()` runs `command.upgrade(cfg, "head")` and nothing else.
- [x] `backup.create_backup_copy()` produces a `.dump` file that round-trips via
      `pg_restore` into a fresh DB; row counts match.
- [x] `inspection.check_integrity()` returns `(True, "ok")` on a healthy DB and
      reports a real reason on a fault (covered by a unit test that points it at
      a deliberately-bad DSN).
- [x] No `asyncio.to_thread(...)` remains under `app/db/`.
- [x] `tests/db/test_runtime_services_postgres.py` exercises every service
      against an ephemeral Postgres in CI.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the DB runtime/service entries under Raw SQL, Pragmas, Healthchecks, and
  `asyncio.to_thread`.
- `pg_dump` requires the binary. If we choose host-side execution, no Dockerfile
  changes are needed; if container-side, add `postgresql-client` to a dedicated
  utility stage (do **not** bloat the bot image — use a separate
  `ratatoskr-pgtools` profile in compose).
- The `xact_rollback` heuristic for `check_integrity` is approximate; a
  follow-up could read `pg_stat_database_conflicts` for replicas. Out of scope
  for this migration.

## Review evidence

- Rewrote runtime services around `AsyncEngine` / `async_sessionmaker`; `Database`
  now exposes `executor`, `bootstrap`, `maintenance`, `inspection`, and `backups`
  backed by those services.
- Backup decision: prefer host `pg_dump` when installed, otherwise stream
  `pg_dump --format=custom` from the dedicated `ratatoskr-postgres` container.
- Removed obsolete `AsyncRWLock` tests/imports and verified
  `rg -n "app\\.db\\.rw_lock|AsyncRWLock|rw_lock" app tests` returns no matches.
- Verified `rg -n "asyncio\\.to_thread" app/db` returns no matches.
- Verified live Postgres runtime service tests:
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/db/test_runtime_services_postgres.py -q`
  → `3 passed`.
- Verified focused live DB suite:
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/db/test_sqlalchemy_session_factory.py tests/db/test_models_core.py tests/db/test_models_features.py tests/db/test_topic_search_manager.py tests/db/test_runtime_services_postgres.py -q`
  → `11 passed`.
- Deleted obsolete Peewee-only `app/db/health_check.py` and
  `app/db/database_diagnostics.py`; runtime health/diagnostics now go through
  `app/db/runtime/inspection.py` and `app/api/routers/health.py`.
- Verified this removal with focused ruff, focused mypy with skipped imports,
  and `pytest tests/test_health_router_postgres.py` → `1 passed`.
- Deleted obsolete SQLite maintenance and startup schema-coercion helpers
  (`app/db/database_maintenance.py`, `app/db/schema_migrator.py`); maintenance
  now lives in `app/db/runtime/maintenance.py` and Alembic owns schema changes.
- Verified this removal with focused ruff and focused mypy over the async DB
  runtime/session modules.

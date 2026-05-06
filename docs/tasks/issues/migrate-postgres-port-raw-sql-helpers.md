---
title: Port raw SQL call sites to SQLAlchemy text
status: backlog
area: db
priority: medium
owner: Nikita Pochaev
blocks: []
blocked_by:
  - migrate-postgres-port-application-call-sites
  - migrate-postgres-audit-sqlite-surface
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Port raw SQL call sites to SQLAlchemy text #repo/ratatoskr #area/db #status/backlog 🔼

## Objective

Sweep up the remaining direct `database.execute_sql(...)` and `sqlite3.connect(...)`
callers (outside the legacy migrator) and port them to SQLAlchemy
`text()` expressions executed against the connection or session.

## Context

From the F1 audit, callers include:

- `app/cli/migrations/0*.py` — flagged delete; superseded by the SQLAlchemy
  Alembic baseline (M4).
- `app/cli/add_performance_indexes.py:108` — `sqlite_master` lookup. Replace
  with SQLAlchemy `Inspector` (`from sqlalchemy import inspect`); on Postgres
  list indexes via `inspector.get_indexes(table_name)`.
- `app/db/health_check.py:109` — `PRAGMA foreign_keys`. PG always enforces
  FKs; the check becomes a no-op (return success) with a one-line comment.
- `app/db/alembic_runner.py:41,58` — `sqlite_master` lookups. After M4 + O5,
  this file is superseded; the lookups disappear.
- `app/adapters/digest/session_validator.py:44` — Telethon's own SQLite
  session DB. **Stays SQLite** (out of migration scope). No change here, but
  document the carve-out in `docs/SPEC.md`.
- `app/di/database.py:115,146` — `PRAGMA integrity_check`,
  `peewee.SqliteDatabase`. After F3, this file is rewritten or deleted in
  favour of the new `Database` factory.
- Healthcheck commands in `ops/docker/docker-compose.yml:58,141` — replace
  with `python -m app.cli.healthcheck` (a thin script that opens the
  configured `Database` and runs `SELECT 1`).

## Acceptance criteria

- [x] `app/cli/migrations/0*.py` removed. (Verify with the F1 audit list that
      nothing imports them.)
- [ ] All non-Telethon raw SQL/PRAGMA callers either:
  - replaced with `await connection.execute(text(...))` or `inspector.*` calls,
  - or deleted because the surrounding module is gone.
- [x] Compose healthchecks use `python -m app.cli.healthcheck` against the
      configured `DATABASE_URL`. The script exits non-zero on any error.
- [x] Telethon SQLite carve-out documented in `docs/SPEC.md` and the F1 audit.
- [ ] `git grep -nE "execute_sql|sqlite_master|PRAGMA " app/` returns only
      Telethon-related hits and `app/cli/_legacy_peewee_models/`.
- [ ] `make lint` / `make type` pass.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the Raw SQL, Pragmas, Alembic, Healthchecks, and Telethon Session Caveat
  sections.
Do not invent a SQLite-to-Postgres SQL translator for the deprecated
`app/cli/migrations/` files — those revisions have already been baked into the
SQLAlchemy Alembic baseline (M4), so deletion is the right move.

## Progress

- Ported `app/db/batch_operations.py` from Peewee batch create/update/delete
  calls to SQLAlchemy async sessions while keeping synchronous compatibility
  wrappers for legacy callers.
- Added live Postgres coverage in
  `tests/db/test_batch_operations_postgres.py` for LLM batch insert, request
  status updates, request/summary batch reads, summary read updates, and
  cascading request deletes.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/db/test_batch_operations_postgres.py`
  → `1 passed`, focused ruff, and focused mypy with skipped imports.
- Deleted obsolete SQLite-only `app/cli/add_performance_indexes.py` and its
  SQLite tests; index DDL now lives in the SQLAlchemy Alembic baseline.
- Removed the deprecated CLI command from `docs/reference/cli-commands.md`.
- Deleted deprecated `app/cli/migrations/` scripts and their SQLite-only
  migration tests; the PostgreSQL Alembic baseline now owns live schema DDL.
- Added `app.cli.healthcheck`, which opens the configured SQLAlchemy
  PostgreSQL database and exits non-zero when `Database.healthcheck()` fails.
- Documented the Telethon `.session` SQLite carve-out in `docs/SPEC.md`; those
  files are owned by Telethon and are outside Ratatoskr relational storage.

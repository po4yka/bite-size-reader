---
title: Audit Peewee and SQLite code surface
status: backlog
area: db
priority: high
owner: Nikita Pochaev
blocks:
  - migrate-postgres-introduce-database-factory
  - migrate-postgres-port-models-core
  - migrate-postgres-port-raw-sql-helpers
  - migrate-postgres-port-persistence-repositories
  - migrate-postgres-port-application-call-sites
blocked_by:
  - migrate-postgres-decide-orm-strategy
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Audit Peewee and SQLite code surface #repo/ratatoskr #area/db #status/backlog ⏫

## Objective

Produce a definitive inventory of every Peewee and SQLite call site in the
codebase so the M, R, and O phases have an unambiguous worklist.

## Context

Initial scan during planning surfaced (non-exhaustive):

- `app/db/session.py:71` — `RowSqliteDatabase(_BaseSqliteDatabase)`.
- `app/db/_models_*.py` — every model file imports
  `playhouse.sqlite_ext.JSONField`; `_models_core.py` also imports `FTS5Model`,
  `SearchField`.
- `app/db/topic_search_index.py` — FTS5 `MATCH`, `bm25()`, `'delete-all'`.
- `app/db/alembic_runner.py:41,58` — `sqlite_master`; `sqlite:///` URL.
- `app/db/health_check.py:109` — `PRAGMA foreign_keys`.
- `app/di/database.py:115,146` — `PRAGMA integrity_check`,
  `peewee.SqliteDatabase`.
- `app/cli/migrations/0*.py` — many raw `db._database.execute_sql()` callers
  using SQLite-only DDL.
- `app/adapters/digest/session_validator.py:44` — `PRAGMA table_info(version)`
  against Telethon's session DB (out of migration scope — Telethon does not
  support Postgres sessions).
- `ops/docker/docker-compose.yml:58,141` — `sqlite3.connect()` healthchecks.

The audit also extends to **all Peewee call sites**, not just SQLite-flavoured
code: every `from peewee import …`, every `Model.select()`, every
`asyncio.to_thread(...)` wrapping a Peewee call, every `model_to_dict(...)`
caller. R2 and R3 use this list as their port worklist.

## Acceptance criteria

- [ ] Inventory committed as `docs/explanation/peewee-sqlite-surface-audit.md`
      with sections: model fields, raw SQL, pragmas, FTS5, alembic, healthchecks,
      Peewee imports, `asyncio.to_thread` callers, tests.
- [ ] Each entry cites `file:line` and classifies as: keep-as-is (no migration
      action), replace (M-phase or R-phase target), or delete (legacy/unused).
- [ ] Deprecated `app/cli/migrations/` files are flagged delete (already not run
      per `app/db/schema_migrator.py:6` docstring).
- [ ] Telethon SQLite session DB caveat is recorded explicitly.
- [ ] Audit doc is referenced from each downstream port task as the input list.
- [ ] Counts at the bottom: total Peewee imports, total `asyncio.to_thread`
      callers, total `database.execute_sql` callers — used as a reduction
      progress metric during R-phase implementation.

## Notes

- `rg -n "from peewee"`, `rg -n "playhouse\."`, `rg -n "asyncio\.to_thread"`,
  `rg -n "execute_sql"`, `rg -n "PRAGMA"` are the primary discovery queries.
- Cross-check `tests/` and `clients/cli/` (the renamed CLI directory) too.

---
title: Generate SQLAlchemy Alembic baseline revision
status: backlog
area: db
priority: high
owner: Nikita Pochaev
blocks:
  - migrate-postgres-update-alembic-env
  - migrate-postgres-build-data-migrator
blocked_by:
  - migrate-postgres-port-models-core
  - migrate-postgres-port-models-features
  - migrate-postgres-port-topic-search-model
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Generate SQLAlchemy Alembic baseline revision #repo/ratatoskr #area/db #status/backlog ⏫

## Objective

Produce a single hand-reviewed Alembic baseline revision that creates the full
SQLAlchemy 2.0 schema on an empty Postgres database, replacing the historical
SQLite-flavoured revisions.

## Context

The historical revisions in `app/db/alembic/versions/0001_baseline.py …
0016_015_add_signal_sources.py` were authored against SQLite; some use
`batch_alter_table` and SQLite-specific DDL. Replaying them against Postgres is
fragile and pointless — Peewee's `create_tables(safe=True)` was the source of
truth, not those revisions.

Steps for this task:

1. Spin up an empty Postgres 16 locally via the T1 compose service.
2. Run `alembic revision --autogenerate -m "0001_baseline_sqlalchemy"` against
   the SQLAlchemy `Base.metadata` from M1+M2+M3.
3. Hand-review the generated DDL: ensure FK ondelete, indexes, generated
   columns (`body_tsv`), default callables, sequence ownership, and table
   ordering match expectations.
4. Move the existing 16 revisions under
   `app/db/alembic/versions/_legacy_sqlite/` (do **not** delete — keep for
   audit/history; their `down_revision` chain becomes irrelevant once
   `_legacy_sqlite/` is excluded from Alembic's script directory).
5. Configure Alembic so the new baseline is the only active revision.

## Acceptance criteria

- [ ] `app/db/alembic/versions/0001_baseline_sqlalchemy.py` exists, hand-reviewed
      and committed.
- [ ] Running `alembic upgrade head` against an empty Postgres creates the full
      schema (49+ tables) cleanly.
- [ ] `app/db/alembic/versions/_legacy_sqlite/` exists and is excluded from
      Alembic's `script_location` (set `version_locations` in `alembic.ini` to
      point only to the new location).
- [ ] `Base.metadata.create_all()` is **not** used at runtime any more — Alembic
      is the only schema authority on Postgres.
- [ ] Test: drop the local Postgres DB, recreate empty, run `alembic upgrade
      head`, run M1+M2+M3 fixture tests — all green.

## Notes

- Generated `body_tsv` columns sometimes confuse autogenerate; if it tries to
  drop and recreate, fix by hand and document the workaround inline.
- After this task, `app/db/alembic_runner.py`'s elaborate stamp-or-upgrade logic
  (designed to coexist with the legacy `migration_history` table) collapses to
  `command.upgrade(cfg, "head")` — that simplification lives in O5.

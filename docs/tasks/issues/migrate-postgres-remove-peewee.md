---
title: Remove Peewee dependency and legacy snapshot
status: backlog
area: db
priority: medium
owner: Nikita Pochaev
blocks:
  - migrate-postgres-update-docs
blocked_by:
  - migrate-postgres-execute-pi-cutover
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Remove Peewee dependency and legacy snapshot #repo/ratatoskr #area/db #status/backlog 🔼

## Objective

Remove `peewee` from the project after the Pi has been on Postgres + SQLAlchemy
for ≥ 30 days without rollback, including the legacy Peewee snapshot used by
the data migrator and the archived SQLite-flavoured Alembic revisions.

## Context

After the cutover (C2) succeeds, three pieces of legacy code remain in-repo
deliberately:

- `app/cli/_legacy_peewee_models/` — the frozen Peewee snapshot the migrator
  reads from. Useful only if a re-migration is ever needed (e.g. importing a
  subset of historical data from a different SQLite source).
- `app/cli/migrate_sqlite_to_postgres.py` — the migrator itself.
- `app/db/alembic/versions/_legacy_sqlite/` — archived revisions, excluded
  from `version_locations`.

This task removes them — but only after the deployment is demonstrably stable.
Define stable as: 30 calendar days on Postgres without invoking the rollback
path; no production incident traceable to the migration; topic search,
summary creation, and sync flows healthy across the period.

## Acceptance criteria

- [ ] `peewee` removed from `pyproject.toml`; `uv lock` regenerated.
- [ ] `app/cli/_legacy_peewee_models/` directory deleted.
- [ ] `app/cli/migrate_sqlite_to_postgres.py` deleted.
- [ ] `app/db/alembic/versions/_legacy_sqlite/` directory deleted.
- [ ] `git grep -nE "peewee|playhouse" .` returns zero hits across the repo.
- [ ] `make lint`, `make type`, `pytest -q` all green.
- [ ] CI completes without the legacy migrator path; CI image size drops by
      the wheel size of `peewee`.
- [ ] Note added to the migration plan document recording the date and final
      LOC delta.

## Notes

Do **not** execute this task earlier — keeping the migrator code present for
30 days is cheap insurance. If the Postgres instance ever needs to be
rebuilt from the original SQLite snapshot, the migrator is the only practical
path.

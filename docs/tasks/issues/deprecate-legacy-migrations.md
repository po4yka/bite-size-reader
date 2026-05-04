---
title: Deprecate app/cli/migrations/ in favour of Alembic exclusively
status: backlog
area: db
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Deprecate app/cli/migrations/ in favour of Alembic exclusively #repo/ratatoskr #area/db #status/backlog ⏫

## Objective

Two parallel migration systems exist with matching numbering (`app/cli/migrations/` with 15 Python scripts, and `app/db/alembic/` with 16 Alembic revisions). New contributors cannot determine which is authoritative. The legacy runner is still referenced in some paths, creating confusion about the upgrade path.

## Context

- `app/cli/migrations/` — legacy Python runner (001–015)
- `app/db/alembic/` — Alembic (0001_baseline through 0016); authoritative
- `app/db/schema_migrator.py` — third system for JSON coercion, runs on every startup

## Acceptance criteria

- [ ] `app/cli/migrations/` is removed or moved to `app/cli/migrations/_deprecated/` with a README explaining it is superseded by Alembic
- [ ] All references to `migration_runner.py` are removed from active code paths
- [ ] `docs/SPEC.md` updated to document Alembic as the sole migration system
- [ ] `schema_migrator.py` (JSON coercion) documented as a startup maintenance task, not a migration system

## Definition of done

`fd migration app/cli/` shows only Alembic-related files; no legacy runner is reachable from any startup path.

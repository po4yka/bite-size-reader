---
title: Add Alembic migration smoke test to CI (upgrade head + downgrade)
status: backlog
area: ci
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add Alembic migration smoke test to CI (upgrade head + downgrade) #repo/ratatoskr #area/ci #status/backlog ⏫

## Objective

No CI job ever runs Alembic migrations. A broken migration only surfaces on production deployment. Adding a migration smoke test catches schema regressions before they reach users.

## Context

- `.github/workflows/ci.yml` — no migration job exists
- `app/db/alembic/` — 16 versioned revisions with `downgrade()` implementations

## Acceptance criteria

- [ ] New CI job runs `alembic upgrade head` against a fresh temp SQLite database
- [ ] Job then runs `alembic downgrade -1` to verify the last downgrade path
- [ ] Job fails the pipeline if either command exits non-zero
- [ ] Job runs on every PR, not just on main

## Definition of done

A deliberately broken migration (e.g. invalid SQL) causes the CI job to fail before merge.

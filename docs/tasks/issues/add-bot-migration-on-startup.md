---
title: Add alembic upgrade head to bot container startup
status: backlog
area: ops
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add alembic upgrade head to bot container startup #repo/ratatoskr #area/ops #status/backlog ⏫

## Objective

The bot container CMD never runs database migrations. Only `Dockerfile.api` runs `python -m app.cli.migrate_db` before starting uvicorn. A user running only the bot container on an outdated schema silently gets undefined behavior or crashes.

## Context

- `ops/docker/Dockerfile` — bot CMD: starts taskiq worker + scheduler + `python -m bot` with no migration step
- `ops/docker/Dockerfile.api` — CMD: runs `python -m app.cli.migrate_db` then uvicorn
- `app/db/alembic/` — Alembic is the authoritative migration system

## Acceptance criteria

- [ ] Bot container CMD runs `alembic upgrade head` (or equivalent via `app.cli.migrate_db`) before starting bot processes
- [ ] If migrations have already run, startup is not meaningfully slower (Alembic no-ops on current head)
- [ ] Migration failure causes the container to exit with a non-zero code, not silently continue

## Definition of done

Fresh bot container against an empty database applies all migrations and starts successfully.

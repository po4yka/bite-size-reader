---
title: Port application call sites to AsyncSession
status: backlog
area: db
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-build-data-migrator
  - migrate-postgres-add-test-fixtures-and-ci
blocked_by:
  - migrate-postgres-port-persistence-repositories
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Port application call sites to AsyncSession #repo/ratatoskr #area/db #status/backlog 🔺

## Objective

Rewrite every direct ORM call outside the persistence layer — in `app/api/`,
`app/adapters/`, `app/agents/`, `app/cli/` (excluding the legacy migrator),
`app/application/`, and `app/domain/services/` — from Peewee to SQLAlchemy 2.0
`AsyncSession`.

## Context

The F1 audit produces the worklist. Major touchpoints (non-exhaustive):

- `app/api/routers/*.py` — replace any direct `Model.get(...)` with
  `Depends(get_session_for_request)` and `await session.scalar(...)` patterns.
- `app/api/services/*.py` — same, but with explicit `Database`-injected sessions.
- `app/adapters/telegram/message_router.py`, `command_handlers/*.py` — open a
  transaction per inbound message, pass to use cases.
- `app/adapters/digest/`, `app/adapters/content/`, `app/adapters/youtube/` —
  background tasks; per-operation `async with database.transaction():`.
- `app/agents/` — per-step `async with database.session():`.
- `app/cli/summary.py`, `app/cli/backfill_*.py`, `app/cli/migrate_db.py`,
  `app/cli/mcp_server.py` — top-level `asyncio.run(...)` boundary opens the DB
  facade and tears it down on exit.
- `app/application/use_cases/*.py` — orchestrate transactions for multi-repo
  flows.
- `app/domain/services/*.py` — port any persistence-touching code; pure-domain
  services should not need changes.

Port in module-scoped batches; after each batch, run that module's tests and
commit. The order is defined by R2's repository surface — modules that depend on
the most-ported repository are easiest to land first.

## Acceptance criteria

- [ ] `git grep -nE "from peewee" app/` returns zero hits (excluding
      `app/cli/_legacy_peewee_models/`).
- [ ] `git grep -nE "playhouse\." app/` returns zero hits (same exclusion).
- [ ] `git grep -nE "asyncio\.to_thread" app/` returns zero hits in the data
      path (`tests/` may keep them; document any remaining and justify).
- [ ] Type-check (`make type`) is clean.
- [ ] Full test suite passes against Postgres (T3 CI job is green).
- [ ] No use of bare `Model.create(...)` / `Model.get(...)` /
      `Model.select()` syntax outside `app/cli/_legacy_peewee_models/`.
- [ ] `app/cli/summary.py` end-to-end run against a local Postgres produces a
      summary indistinguishable from the SQLite output.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the DI/API, Telegram/messaging/rules, CLI/MCP, cache, and application-service
  entries under Peewee Imports and `asyncio.to_thread`.
- This task is large; split implementation into PRs by directory
  (`app/api/`, `app/adapters/`, etc.) for reviewability. The acceptance
  criteria are checked at the end of the last PR.
- Watch for code that grabs `model.dict()`-style outputs via the old
  `model_to_dict` helper — its replacement should iterate
  `Mapped` columns from the model's `__table__.columns`.

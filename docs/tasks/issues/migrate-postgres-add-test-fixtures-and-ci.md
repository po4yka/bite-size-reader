---
title: Add async Postgres test fixtures and CI
status: backlog
area: testing
priority: medium
owner: Nikita Pochaev
blocks:
  - migrate-postgres-write-pi-runbook
blocked_by:
  - migrate-postgres-port-application-call-sites
  - migrate-postgres-port-topic-search-model
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Add async Postgres test fixtures and CI #repo/ratatoskr #area/testing #status/backlog 🔼

## Objective

Replace the existing Peewee-on-SQLite test fixtures with async SQLAlchemy
fixtures backed by an ephemeral Postgres, and add a CI job that runs the full
suite against Postgres on every PR.

## Context

After R3 lands, no application code uses SQLite. The test suite must follow.
Existing helpers in `tests/db_helpers.py` are Peewee-flavoured CRUD wrappers
(`create_request`, `insert_summary`, etc.) — these get rewritten to use
`AsyncSession`.

Approach:

- **Per-test schema**: each test gets a fresh schema using a `TRUNCATE` cascade
  of all tables in `Base.metadata.sorted_tables` reversed. Faster than
  drop/recreate per test; isolated enough for unit tests.
- **Per-suite database**: the GitHub Actions `services: postgres:16-alpine`
  pattern boots one Postgres for the suite. CI sets
  `DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/ratatoskr_test`.
- **`pytest-asyncio`** in `auto` mode for the async test functions.
- **Fixtures**:
  - `database` (session-scoped): a `Database` instance pointed at the test DSN
    + Alembic upgrade-to-head.
  - `session` (function-scoped): yields a fresh `AsyncSession` and truncates
    after.
  - `db_helpers` (function-scoped): the rewritten CRUD helpers, now async,
    accepting a `session` and operating via SQLAlchemy.
- **Topic search regression set**:
  `tests/fixtures/topic_search_queries.json` — 10 query/expected-id pairs
  derived from a sanitised snapshot of production data (request IDs only, no
  content). Used by M3 and T2 acceptance.

## Acceptance criteria

- [ ] `tests/conftest.py` provides `database`, `session`, and `db_helpers`
      fixtures per the Approach above.
- [ ] `tests/db_helpers.py` rewritten — every helper is `async`, takes a
      `session: AsyncSession`, and uses SQLAlchemy `insert(...) /
      select(...) / update(...)`.
- [ ] No `:memory:`, `SqliteDatabase`, or `peewee` references remain in
      `tests/` (excluding any tests that target the legacy migrator's read
      side, which are clearly named `test_legacy_*.py`).
- [ ] CI matrix: `.github/workflows/ci.yml` includes a `services:
      postgres:16-alpine` job that runs `pytest -q` with
      `RATATOSKR_TEST_BACKEND=postgres` (kept as an env even if always
      Postgres now, for forward compatibility).
- [ ] `tests/fixtures/topic_search_queries.json` exists with 10 pairs.
- [ ] Coverage of touched paths is at or above pre-migration levels.
- [ ] `pytest -q` runtime increase is ≤ 50% relative to today (Postgres start
      cost dominates per-suite, not per-test).

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the Tests section and the count metrics used to verify Peewee/SQLite removal
  from `tests/`.
- For local dev parity, add `make test-postgres` that boots the compose
  postgres service and runs `pytest -q` against it, so contributors don't
  need to wait for CI.
- `expire_on_commit=False` on the test session is consistent with the
  production session; tests should not rely on auto-refresh.

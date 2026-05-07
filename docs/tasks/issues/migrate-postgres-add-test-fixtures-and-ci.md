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

## Pre-existing defensive shim (2026-05-06)

To unblock test collection mid-migration, ~30 test files in `tests/` were
patched to import `database_proxy`, `model_to_dict`, and the Peewee model
classes (`Request`, `Summary`, `User`, `Channel`, `ChannelSubscription`,
`ClientSecret`, `CrawlResult`, `LLMCall`, etc.) from
`app.cli._legacy_peewee_models` instead of `app.db.models`, and
`DatabaseSessionManager` imports were wrapped in `try/except ImportError` with
a `None` fallback. This is a stop-gap, not the T3 port — test bodies still
exercise Peewee CRUD against an in-memory SQLite-backed `database_proxy`.
When this task lands, every redirected import must be replaced with the new
async helpers and every `try/except ImportError` shim around
`DatabaseSessionManager` must be removed (the class no longer exists).
Touched files were enumerated in the commit that introduced the shim.

## Phase 1 foundation landed (2026-05-07)

The async-Postgres test scaffolding is now in place, with no caller
test bodies touched yet:

- `tests/db_helpers_async.py` — every public helper from
  `tests/db_helpers.py` (~20 functions) ported to
  `async def helper(session: AsyncSession, ...)` against
  `app.db.models` SQLAlchemy ORM. Mirrors the original API name-for-name
  so caller migration is mechanical (`create_request(**kw)` →
  `await create_request(session, **kw)`).
- `tests/conftest.py` — added two new async fixtures gated on
  `TEST_DATABASE_URL`:
  - `database` (session-scoped, loop-scoped session): builds a
    `Database` from the env DSN, runs `await db.migrate()` once, yields,
    disposes on teardown.
  - `session` (function-scoped, loop-scoped session): yields an
    `AsyncSession`; on teardown rolls back and runs
    `TRUNCATE TABLE … RESTART IDENTITY CASCADE` over every table in
    `Base.metadata.sorted_tables[::-1]` for clean isolation.
  Both fixtures `pytest.skip(...)` when `TEST_DATABASE_URL` is unset, so
  unit tests not needing a DB keep running on developer laptops without
  Postgres.
- `tests/fixtures/topic_search_queries.json` — 10-entry skeleton with
  `_status` placeholder; entries to be populated from a sanitised
  production snapshot before topic-search regression checks consume it.

What is NOT yet done (open Phase 2+ work):

- Caller test bodies (~30 files) still import from
  `tests/db_helpers.py` (the legacy shim) and exercise Peewee CRUD via
  `app.cli._legacy_peewee_models`. They need to be migrated one batch
  at a time: switch the import to `tests/db_helpers_async`, change the
  test body to `async def`, take the `session` fixture, `await` each
  helper. Each migration batch should be verified against a live
  Postgres (`TEST_DATABASE_URL` set) before commit.
- The legacy `tests/db_helpers.py` file remains in place and unchanged;
  it is deleted only when no caller still imports it.
- `tests/fixtures/topic_search_queries.json` still has placeholder
  entries; populating it requires access to a production snapshot.
- CI matrix: no `services: postgres:16-alpine` job has been added to
  `.github/workflows/ci.yml` yet. That is the final Phase 3 step,
  blocked on the caller migration so the new fixtures actually run.

# PostgreSQL Migration CI Validation — Design Spec

**Date:** 2026-05-15 **Status:** Draft

---

## Problem

The `migration-smoke-test` CI job is non-functional. It sets a `DB_PATH` SQLite env var and calls `DatabaseSessionManager(path=...)` — an API that no longer exists in the PostgreSQL-era codebase. The bare `alembic` commands run with no `DATABASE_URL`, causing `alembic_runner` to throw `"postgresql+asyncpg:// URL required"` immediately. The job has been passing (or silently failing) without validating anything meaningful.

---

## Goal

Replace the stale job with a PostgreSQL-backed Alembic validation that:

1. Spins up a real PostgreSQL 16 service container in CI.
2. Runs `alembic upgrade head` against it via the existing `app.cli.migrate_db` CLI.
3. Performs a round-trip `downgrade -1 → upgrade head` to exercise rollback paths.
4. Asserts `alembic current` resolves to `(head)` — confirming the run completed.
5. Blocks `status-check` (and therefore the branch) if any step fails.

---

## Scope

### In scope

- Replace `migration-smoke-test` job in `.github/workflows/ci.yml`.
- Fix `tests/cli/test_migrate_db_cli.py` to remove stale SQLite path assumptions.
- No new application code; no changes to `alembic_runner.py`, `env.py`, or migrations.

### Out of scope

- Adding PostgreSQL to the unit-test or integration-test jobs.
- API/bot healthcheck against the migrated DB (no application process needed here).
- Schema drift detection (separate concern).

---

## Design

### CI job: `migration-smoke-test`

**Services block** (new):

```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: ratatoskr_ci
    options: >-
      --health-cmd pg_isready
      --health-interval 10s
      --health-timeout 5s
      --health-retries 5
    ports:
      - 5432:5432
```

**Env var** (replaces `DB_PATH`):

```yaml
env:
  DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/ratatoskr_ci
```

This variable is read by both `app/db/alembic/env.py` (`_get_db_url`) and `app/db/alembic_runner.py` (`_resolve_dsn`), so neither the CLI nor bare `alembic` commands need additional flags.

**Steps** (replacing the two stale steps):

1. **Upgrade to head** — `python -m app.cli.migrate_db` Exercises the production migration path; fails on any SQL error.

2. **Downgrade one step** — `alembic downgrade -1` Validates the most-recent migration's `downgrade()` function. All 13 revisions have real downgrade implementations (no `pass` bodies), so this is safe.

3. **Upgrade back to head** — `alembic upgrade head` Confirms the round-trip restores a clean schema.

4. **Assert at head** — `alembic current 2>&1 | grep -q "(head)"` Hard assertion that the CLI ran to completion and Alembic's revision pointer is at `0013`.

Steps 1–4 run sequentially under a single `Run` step with `set -euo pipefail`.

**Unchanged steps**: checkout, download-artifact, setup-python, install-uv, install-deps.

**Timeout**: raise from 10 m to 15 m (PG service startup + asyncpg install can be slow on cold runners).

### Unit test fix: `tests/cli/test_migrate_db_cli.py`

Both tests mock `upgrade_to_head` / `print_status` — no real DB is touched. The only issue is that the test asserts the mocked function receives a SQLite file path (`/tmp/test.db`, `status.sqlite`), which implies the CLI accepts file paths. It should assert a PostgreSQL DSN instead.

**`test_main_runs_shared_migration_flow_once`**:
- Change `sys.argv` arg to `"postgresql+asyncpg://user:pass@localhost:5432/test"`
- Update assertion: `captured["db_path"] == "postgresql+asyncpg://user:pass@localhost:5432/test"`

**`test_migrate_db_status_reports_migration_state`**:
- Remove `tmp_path / "status.sqlite"` fixture usage (unused after the fix)
- Change `sys.argv` arg to `"postgresql+asyncpg://user:pass@localhost:5432/test"`

The mocks remain in place — these tests verify CLI routing and argument plumbing, not DB behavior.

---

## Failure modes

| Failure | Signal |
|---------|--------|
| Missing migration revision file | `alembic upgrade head` exits non-zero |
| Broken `upgrade()` SQL | `python -m app.cli.migrate_db` exits non-zero |
| Broken `downgrade()` SQL | `alembic downgrade -1` exits non-zero |
| Alembic stuck mid-migration | `alembic current` output lacks `(head)` → grep fails |
| PG service never healthy | `--health-retries 5` exhausted → job fails before any step runs |

---

## What does not change

- `alembic_runner.py`, `env.py`, `alembic.ini` — no changes needed.
- All 13 migration files — untouched.
- `status-check` job — `migration-smoke-test` is already in its `needs` list.
- `pr-summary` job — does not reference `migration-smoke-test`.

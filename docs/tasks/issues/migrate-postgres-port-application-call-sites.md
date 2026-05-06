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

## Progress

- Removed FastAPI app-level Peewee exception registration in favor of
  `SQLAlchemyError`, and ported `SystemMaintenanceService` from SQLite file
  inspection/backup to PostgreSQL runtime inspection and `pg_dump` backup
  creation.
- Updated `/v1/system/db-info` and admin system metrics to await the async
  PostgreSQL DB info path.
- Verified this slice with focused service tests
  (`pytest --confcutdir=tests/api/services tests/api/services/test_system_maintenance_service.py`
  → `6 passed`), runtime Postgres smoke tests
  (`TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/db/test_runtime_services_postgres.py`
  → `3 passed`), focused ruff, and focused mypy with skipped imports.
- Ported API health database checks from SQLite `execute_sql` and
  `asyncio.to_thread` to native async PostgreSQL `Database.healthcheck()` and
  inspection calls, with cached detailed diagnostics still preserved.
- Verified this slice with
  `pytest tests/test_health_router_postgres.py` → `1 passed`, focused ruff,
  focused mypy with skipped imports, and `python -c 'import app.api.main'`.
- Ported Telegram admin DB diagnostics from sync inspection wrappers to async
  PostgreSQL inspection methods, and added
  `DatabaseInspectionService.async_verify_processing_integrity()` for async
  command handlers.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/db/test_runtime_services_postgres.py`
  → `3 passed`, focused ruff, and focused mypy with skipped imports.
- Removed two remaining runtime `.path` assumptions from the API lifespan and
  Telegram bot database backup loop; Telegram scheduled backups now create
  PostgreSQL `.dump` files through `Database.create_backup_copy()`.
- Verified this slice with focused ruff, focused mypy with skipped imports, and
  imports for `app.api.main` and `TelegramBot`.
- Replaced stale type-only `DatabaseSessionManager` references across API,
  Telegram, RSS, attachment, content, export, sync, background processing, and
  message-persistence call sites with the SQLAlchemy `Database` facade type.
- Verified this slice with focused ruff, focused mypy with skipped imports, and
  import smoke checks for representative touched modules.
- Updated digest subscribe/unsubscribe callers to use the new async
  SQLAlchemy-backed digest subscription helpers in Telegram handlers and removed
  the digest channel service's Peewee integrity handling.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_digest_subscription_ops_postgres.py`
  → `2 passed`, focused ruff, focused mypy with skipped imports, and digest
  import smoke checks.
- Removed SQLite-specific OpenTelemetry instrumentation from runtime tracing
  configuration and regenerated `uv.lock`/`requirements-all.txt` without
  `opentelemetry-instrumentation-sqlite3`.
- Replaced the digest category service's Peewee integrity exception handling
  with SQLAlchemy `IntegrityError`; verified with focused ruff, focused mypy,
  and an import smoke check.
- Moved async digest runtime call sites onto the SQLAlchemy-backed
  `SqliteDigestStore.async_*` methods: channel reader post persistence and
  signal mirroring, analyzer cache/write paths, delivery record creation,
  Telegram `/cdigest` and `/channels`, API channel resolve/trigger execution,
  and scheduled digest user enumeration.
- Replaced the Taskiq dependency provider's removed `DatabaseSessionManager`
  import with the SQLAlchemy `Database` facade.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_digest_store_postgres.py tests/infrastructure/test_digest_subscription_ops_postgres.py tests/tasks/test_digest_task.py`
  → `6 passed`, focused ruff, and focused mypy with skipped imports.
- Replaced remaining `DatabaseSessionManager` type annotations in DI modules
  and the RSS Taskiq task with the SQLAlchemy `Database` facade.
- Verified this slice with focused ruff, focused mypy with skipped imports, and
  DI import smoke checks; direct `app.tasks.rss` import still requires the
  optional `taskiq` dependency in this environment.
- Replaced the stale `DatabaseSessionManager` annotation in
  `app/db/user_interactions.py` with the SQLAlchemy `Database` facade; verified
  with focused ruff, focused mypy, and an import smoke check.
- Ported `app/cli/search.py` and `app/cli/search_compare.py` from SQLite
  `--db` paths and `DatabaseSessionManager` construction to the SQLAlchemy
  `Database` facade built from `DATABASE_URL` or `--dsn`.
- Verified this CLI slice with focused ruff, focused mypy, and
  `pytest tests/cli/test_search_cli_module.py tests/cli/test_search_compare_cli_module.py`
  → `7 passed`.

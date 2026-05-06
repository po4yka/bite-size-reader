---
title: Port persistence repositories to AsyncSession
status: doing
area: db
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-port-application-call-sites
blocked_by:
  - migrate-postgres-port-models-features
  - migrate-postgres-port-runtime-services
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Port persistence repositories to AsyncSession #repo/ratatoskr #area/db #status/doing 🔺

## Objective

Rewrite every repository under `app/infrastructure/persistence/` from Peewee model
calls (`Model.select().where(...).execute()`) to SQLAlchemy 2.0 `AsyncSession`
calls (`await session.execute(select(Model).where(...))`).

## Context

`app/infrastructure/persistence/` houses the bulk of the data-access layer
(initial scan during planning showed `sqlite/` and `digest_store.py` and many
sibling modules). The exact set is enumerated by the F1 audit — that list is the
worklist here.

Conventions for the port:

- Constructor takes a `database: Database` (the F3 façade), not an `AsyncSession`.
  Each method opens its own session (or transaction) via `async with
  database.session():` / `database.transaction():`. This keeps the lifetime
  contract local and avoids leaking sessions through layers.
- For multi-call atomicity (e.g. "create request + telegram message together"),
  the use case in `app/application/use_cases/` opens the transaction and passes
  the `AsyncSession` to the repository methods that participate.
- Method signatures may add `*, session: AsyncSession | None = None` for that
  case. When `None`, repository opens its own.
- Read paths use `await session.scalar(select(...))` for single-row,
  `(await session.execute(select(...))).scalars().all()` for lists.
- Writes use `await session.execute(insert(...) / update(...).returning(...))`,
  with `on_conflict_do_update` / `on_conflict_do_nothing` from
  `sqlalchemy.dialects.postgresql.insert` where Peewee used `peewee.ON CONFLICT`.
- Per-row pagination retains its existing semantics (offset/limit or cursor as
  used today — see audit notes).

## Acceptance criteria

- [ ] Every file under `app/infrastructure/persistence/` (per F1 audit) is
      rewritten; no remaining `from peewee` or `playhouse` imports there.
- [ ] Repository tests pass against ephemeral Postgres (extends T3 fixtures).
- [ ] Coverage of touched files matches or exceeds pre-migration coverage.
- [ ] All methods are typed (`async def get_request(self, request_id: int) ->
      Request | None`) — no `Any`-leak from Peewee's loose typing.
- [ ] `git grep -nE "asyncio.to_thread" app/infrastructure/` returns zero hits
      after this task.

## Notes

- Input worklist: `docs/explanation/peewee-sqlite-surface-audit.md`, especially
  the Persistence repositories entries under Peewee Imports, Raw SQL, FTS5, and
  `asyncio.to_thread`.
- Some Peewee idioms have no direct SQLAlchemy equivalent. For
  `Model.update(...).where(...).execute()` (bulk update), use
  `await session.execute(update(Model).where(...).values(...))`.
- Beware `AsyncSession.merge` if you need upsert semantics on a single row;
  prefer `insert(...).on_conflict_do_update(...)` from
  `sqlalchemy.dialects.postgresql` instead — clearer, no extra round-trip.

## Progress

- Ported first core repository slice to SQLAlchemy/AsyncSession while preserving
  existing adapter class names for call-site compatibility:
  `request_repository.py`, `llm_repository.py`, and `crawl_result_repository.py`.
- Added live Postgres tests:
  `tests/infrastructure/test_request_repository_postgres.py` and
  `tests/infrastructure/test_llm_crawl_repositories_postgres.py`.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_request_repository_postgres.py tests/infrastructure/test_llm_crawl_repositories_postgres.py -q`
  → `4 passed`.
- Ported the summary repository to SQLAlchemy/AsyncSession, removed the
  summary-specific Peewee mixins, and replaced the old in-memory SQLite summary
  test with a live Postgres repository test.
- Fixed the SQLAlchemy base update hook so `server_version` updates do not
  overwrite `Summary.version`.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_summary_repository.py -q`
  → `3 passed`.
- Ported `user_repository.py` to SQLAlchemy/AsyncSession and added live
  Postgres coverage for user upserts, link metadata, preferences, chats,
  deletion, and interaction logging.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_user_repository_postgres.py -q`
  → `2 passed`.
- Ported `telegram_message_repository.py` to SQLAlchemy/AsyncSession and
  replaced its structural test with live Postgres coverage for idempotent
  message insert, forward info, and per-user message listing.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_telegram_message_repository.py -q`
  → `2 passed`.
- Removed dead request repository Peewee mixins now that
  `request_repository.py` owns its SQLAlchemy implementation directly.
- Ported `audit_log_repository.py`, `attachment_processing_repository.py`, and
  `video_download_repository.py` to SQLAlchemy/AsyncSession with live Postgres
  coverage for audit JSON insertion, attachment state updates, and video
  download reads/updates.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_media_support_repositories_postgres.py -q`
  → `3 passed`.
- Ported `device_repository.py` to SQLAlchemy/AsyncSession and added live
  Postgres coverage for register, update, upsert, deactivate, last-seen, list,
  and missing-user behavior.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_device_repository_postgres.py -q`
  → `3 passed`.
- Ported `backup_repository.py` and `import_job_repository.py` to
  SQLAlchemy/AsyncSession with live Postgres coverage for backup CRUD/counts and
  import-job progress/status/deletion.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_backup_import_repositories_postgres.py -q`
  → `2 passed`.
- Ported `embedding_repository.py` to SQLAlchemy/AsyncSession with PostgreSQL
  upsert semantics for `summary_embeddings.summary_id` and live coverage for
  embedding upsert/read/list/recent filtering.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_embedding_repository_postgres.py -q`
  → `2 passed`.
- Ported `audio_generation_repository.py` to SQLAlchemy/AsyncSession with
  PostgreSQL upsert semantics for one audio generation row per summary and live
  coverage for started/completed/failed state transitions.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_audio_generation_repository_postgres.py -q`
  → `2 passed`.
- Ported `webhook_repository.py` to SQLAlchemy/AsyncSession with live Postgres
  coverage for subscription lifecycle, delivery logging, failure counters,
  disabling, deletion, and secret rotation.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_webhook_repository_postgres.py -q`
  → `2 passed`.
- Ported `rule_repository.py` to SQLAlchemy/AsyncSession with live Postgres
  coverage for rule CRUD/filtering, soft delete, run-count updates, and
  execution logs.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_rule_repository_postgres.py -q`
  → `2 passed`.

Remaining work: port the rest of `app/infrastructure/persistence/`, remove the
SQLite package/import surface, and replace the skipped SQLite repository tests
with Postgres equivalents.

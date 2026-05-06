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
- Ported `tag_repository.py` to SQLAlchemy/AsyncSession with PostgreSQL
  conflict handling for summary-tag attachments and live coverage for tag CRUD,
  attach/detach/restore, summary counts, tagged summaries, popular-tag listing,
  and tag merge.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_tag_repository_postgres.py -q`
  → `2 passed`.
- Ported `latency_stats_repository.py` to SQLAlchemy/AsyncSession with live
  Postgres coverage for domain, model, global, combined URL-processing, and
  top-domain latency statistics.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_latency_stats_repository_postgres.py -q`
  → `31 passed`.
- Ported `admin_read_repository.py` to SQLAlchemy/AsyncSession with live
  Postgres coverage for admin user counts, job status, content health, system
  metrics, and filtered audit-log reads.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_admin_read_repository_postgres.py -q`
  → `33 passed`.
- Ported `bookmark_import_repository.py` to SQLAlchemy/AsyncSession with
  PostgreSQL conflict handling for imported tags, summary-tag links, and
  collection items.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_bookmark_import_repository_postgres.py -q`
  → `35 passed`.
- Ported `aggregation_session_repository.py` to SQLAlchemy/AsyncSession while
  preserving API/MCP compatibility aliases for `user`, `request`, and
  `aggregation_session` dictionary fields.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_aggregation_session_repository_postgres.py -q`
  → `36 passed`.
- Ported `batch_session_repository.py` to SQLAlchemy/AsyncSession while
  preserving compatibility aliases for batch session/item dictionaries and the
  joined request/summary read shape.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_batch_session_repository_postgres.py -q`
  → `37 passed`.
- Ported `auth_repository.py` to SQLAlchemy/AsyncSession while preserving
  refresh-token cache behavior and compatibility aliases for `user` dictionary
  fields.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_auth_repository_postgres.py -q`
  → `41 passed`.
- Ported `user_content_repository.py` to SQLAlchemy/AsyncSession with live
  Postgres coverage for goals, scoped counts, custom digests, highlights,
  owned-summary checks, and filtered exports.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_user_content_repository_postgres.py -q`
  → `44 passed`.
- Ported `collection_repository.py` to SQLAlchemy/AsyncSession, collapsed the
  old Peewee collection mixins, and preserved compatibility aliases for
  collection, collaborator, invite, and item dictionaries.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_collection_repository.py -q`
  → `47 passed`.
- Ported `rss_feed_repository.py` to SQLAlchemy/AsyncSession with PostgreSQL
  conflict handling for feeds, subscriptions, items, and delivery records while
  preserving RSS subscription/feed compatibility dictionary shapes.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_rss_feed_repository_postgres.py -q`
  → `48 passed`.
- Ported `topic_search_repository.py` to SQLAlchemy/AsyncSession backed by
  PostgreSQL `tsvector`, including indexed search, paginated user-scoped FTS,
  tag refresh, direct document writes, and fallback summary scans.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_topic_search_repository_postgres.py -q`
  → `51 passed`.
- Ported `signal_source_repository.py` to SQLAlchemy/AsyncSession with
  PostgreSQL upserts for sources, subscriptions, feed items, topics, and user
  signals, plus source health, candidate, and feedback workflows.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_signal_source_repository.py -q`
  → `57 passed`.
- Ported `sync_aux_read_adapter.py` to SQLAlchemy/AsyncSession and updated the
  sync auxiliary read port/collector path to await those Postgres-backed reads.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_sync_aux_read_adapter_postgres.py -q`
  → `58 passed`.
- Ported rule support adapters `app/infrastructure/rules/context.py` and
  `app/infrastructure/rules/collection_membership.py` to SQLAlchemy/AsyncSession
  and removed the now-unused `sqlite/base.py` helper.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_rule_support_adapters_postgres.py -q`
  → `60 passed`.
- Ported `smart_collection_handler.py` to SQLAlchemy/AsyncSession and wired it
  with the application `Database` so SummaryCreated smart collection
  auto-population no longer uses Peewee.
- Verified the expanded focused repository suite with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest ... tests/infrastructure/test_smart_collection_handler_postgres.py -q`
  → `61 passed`.
- Ported `push_notification.py` away from its direct Peewee summary lookup by
  using the injected summary repository for async summary reads.
- Verified this slice with
  `pytest tests/infrastructure/test_push_notification_handler.py -q`
  → `2 passed`.
- Ported `trending_cache.py` away from `asyncio.to_thread` + Peewee summary
  scans by querying summaries through the async SQLAlchemy `Database` session
  and wiring the API trending endpoint to the runtime session manager.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/test_trending_topics.py -q`
  → `4 passed`; the expanded focused live suite including recent support
  adapters and handlers passed with `10 passed`.
- Ported `digest_subscription_ops.py` to SQLAlchemy/AsyncSession for channel
  subscribe/unsubscribe lifecycle operations, retaining synchronous wrappers
  for current digest API facade compatibility.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_digest_subscription_ops_postgres.py`
  → `2 passed`, focused ruff, and focused mypy with skipped imports.
- Ported `digest_store.py` off Peewee model calls to SQLAlchemy/AsyncSession
  while preserving synchronous compatibility methods for existing API and bot
  call sites.
- Added live Postgres coverage for digest categories, subscriptions,
  preferences, deliveries, channel posts, cached analyses, and signal-source
  mirroring.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_digest_store_postgres.py tests/infrastructure/test_digest_subscription_ops_postgres.py`
  → `4 passed`.
- Ported `backup_archive_service.py` from Peewee model calls to SQLAlchemy
  async sessions, retained synchronous wrappers for archive validation tests,
  and moved API/Telegram backup call sites to the async archive functions.
- Added live Postgres coverage for creating a ZIP backup archive and updating
  the `user_backups` row.
- Verified this slice with
  `TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/infrastructure/test_backup_archive_service_postgres.py tests/test_backup_service.py`
  → `11 passed`, focused ruff, and focused mypy with skipped imports.
- Deleted unused Peewee-era `app/db/video_downloads.py`; video download
  persistence now goes through the SQLAlchemy repository covered by
  `tests/infrastructure/test_media_support_repositories_postgres.py`.

Remaining work: port the rest of `app/infrastructure/persistence/`, remove the
SQLite package/import surface, and replace the skipped SQLite repository tests
with Postgres equivalents.

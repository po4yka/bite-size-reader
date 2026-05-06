# Peewee and SQLite Surface Audit

Created: 2026-05-06 · Last refreshed: 2026-05-06

This is the F1 inventory for the SQLite -> PostgreSQL and Peewee ->
SQLAlchemy 2.0 migration. It classifies current Peewee and SQLite surfaces as:

- `replace`: port during the M, R, O, or T migration phases.
- `delete`: remove because the code is deprecated or superseded.
- `keep-as-is`: intentionally remains SQLite-specific or outside relational DB scope.

## Current state (2026-05-06)

Most `replace`/`delete` rows in this document are now satisfied. The discovery
commands below are the source of truth — re-run them to confirm the live
state. The detailed tables in the rest of this document remain for
historical context and to map original audit lines to the tasks that
addressed them.

Live grep results as of 2026-05-06:

- `rg -n "from peewee|import peewee|playhouse\." app/` → zero hits outside
  `app/cli/_legacy_peewee_models/` and the (not-yet-built) data migrator
  (T2). `app/cli/_legacy_peewee_models/` is intentional and is removed in
  L1 (`migrate-postgres-remove-peewee`) after the 30-day stability window.
- `rg -n "\.select\(\)\.where|\.get_or_none\(|\.update\(.*\)\.where\(.*\)\.execute" app/` →
  zero hits outside legacy.
- `rg -n "execute_sql|sqlite_master|PRAGMA " app/` → matches only
  `app/adapters/digest/session_validator.py:44` (Telethon session DB —
  documented `keep-as-is`) and `app/db/alembic/versions/_legacy_sqlite/`
  (archived revisions per M4).
- `rg -n "asyncio\.to_thread" app/infrastructure/` → 9 hits, all in
  embedding/search/audio/push/qdrant/messaging — non-DB IO/CPU thread
  bouncing for libraries without async APIs (sentence-transformers, FCM
  send, qdrant-client). Out of scope for the DB migration.

Status snapshot of the migration tasks (per
`docs/tasks/issues/migrate-postgres-*.md`):

| Phase | Task | Status |
| --- | --- | --- |
| F1–F3, M1–M4 | foundation + model layer | done |
| R1 | runtime services | review |
| R2 | persistence repositories | review |
| R3 | application call sites | backlog (surface complete; pending T3 for full acceptance) |
| O2 | raw SQL helpers | review |
| O5 | alembic env update | done in code |
| T1 | compose service | review |
| T2 | data migrator | not started — required for cutover |
| T3 | test fixtures | not started — defensive shim in place since 2026-05-06 |
| C1, C2 | runbook + cutover | pending T2/T3 |
| L1, L2 | cleanup + docs | pending C2 |

### Notable carve-outs

- Telethon's session DB (`*.session` SQLite files used by the digest userbot)
  is `keep-as-is`. Telethon does not support Postgres sessions; the
  validator at `app/adapters/digest/session_validator.py` continues to use
  `sqlite3.connect`.
- `app/db/alembic/versions/_legacy_sqlite/` is archived (not deleted) per M4
  decision; revisions are excluded from `version_locations` and will be
  removed in L1.

Discovery commands:

- `rg -n "^\s*(from peewee import|import peewee|from peewee$|import peewee$)|playhouse\." app tests`
- `rg -n "asyncio\.to_thread|_asyncio\.to_thread" app tests`
- `rg -n "execute_sql|PRAGMA|sqlite_master|sqlite_sequence|sqlite3|sqlite:///|SqliteDatabase|FTS5Model|SearchField|\bMATCH\b|bm25\(|delete-all|model_to_dict" app tests ops`

## Model Fields

All Peewee model definitions are `replace` targets for M1, M2, and M3.

| Classification | Entry |
| --- | --- |
| replace | `app/db/_models_base.py:8` imports Peewee and `app/db/_models_base.py:26` defines `BaseModel(peewee.Model)`. Its timestamp and monotonic `server_version` behavior must move to SQLAlchemy defaults/events. |
| replace | `app/db/_models_base.py:52` defines `model_to_dict`; replace with a SQLAlchemy serialization helper or DTO construction at repository boundaries. |
| replace | `app/db/_models_core.py:5` imports Peewee; `app/db/_models_core.py:6` imports `FTS5Model`, `JSONField`, and `SearchField`; `app/db/_models_core.py:17` through `app/db/_models_core.py:441` define the core models. |
| replace | `app/db/_models_core.py:236` defines `TopicSearchIndex(FTS5Model)`; this is M3, not M1. |
| replace | `app/db/_models_core.py:239` through `app/db/_models_core.py:246` define FTS5 `SearchField` columns. |
| replace | `app/db/_models_aggregation.py:5` imports Peewee; `app/db/_models_aggregation.py:6` imports `JSONField`; `app/db/_models_aggregation.py:12` and `app/db/_models_aggregation.py:48` define aggregation models. |
| replace | `app/db/_models_batch.py:5` imports Peewee; `app/db/_models_batch.py:6` imports `JSONField`; `app/db/_models_batch.py:12` and `app/db/_models_batch.py:42` define batch models. |
| replace | `app/db/_models_collections.py:5` imports Peewee; `app/db/_models_collections.py:6` imports `JSONField`; `app/db/_models_collections.py:12`, `app/db/_models_collections.py:44`, `app/db/_models_collections.py:61`, and `app/db/_models_collections.py:82` define collection models. |
| replace | `app/db/_models_digest.py:5` imports Peewee; `app/db/_models_digest.py:6` imports `JSONField`; `app/db/_models_digest.py:12` through `app/db/_models_digest.py:133` define digest models. |
| replace | `app/db/_models_rss.py:5` imports Peewee; `app/db/_models_rss.py:12` through `app/db/_models_rss.py:71` define RSS models. |
| replace | `app/db/_models_rules.py:5` imports Peewee; `app/db/_models_rules.py:6` imports `JSONField`; `app/db/_models_rules.py:12` through `app/db/_models_rules.py:141` define rule/import/backup models. |
| replace | `app/db/_models_signal.py:5` imports Peewee; `app/db/_models_signal.py:6` imports `JSONField`; `app/db/_models_signal.py:14` through `app/db/_models_signal.py:150` define signal models. |
| replace | `app/db/_models_user_content.py:5` imports Peewee; `app/db/_models_user_content.py:6` imports `JSONField`; `app/db/_models_user_content.py:11` through `app/db/_models_user_content.py:108` define user-content/tag models. |
| replace | `app/db/models.py:12` and `app/db/models.py:128` re-export Peewee models and `model_to_dict`; replace with `app/db/models/` SQLAlchemy package exports. |
| replace | `app/infrastructure/persistence/sqlite/orm_exports.py:15` and `app/infrastructure/persistence/sqlite/orm_exports.py:28` re-export Peewee symbols to repositories and CLIs; replace with SQLAlchemy model imports or delete the module after the repository port. |

## Raw SQL

All non-Telethon raw SQL surfaces are `replace` or `delete` targets for O2/O5.

| Classification | Entry |
| --- | --- |
| replace | `app/db/session.py:245` and `app/db/session.py:251` expose generic `execute`/`fetchone` wrappers over Peewee `execute_sql`; replace with SQLAlchemy connection/session execution. |
| replace | `app/db/topic_search_index.py:134`, `app/db/topic_search_index.py:180`, `app/db/topic_search_index.py:237`, and `app/db/topic_search_index.py:244` execute raw FTS5 maintenance/search SQL; replace in M3. |
| replace | `app/db/database_diagnostics.py:338` executes diagnostic SQL through Peewee; port to SQLAlchemy `text()` or SQLAlchemy inspector APIs. |
| replace | `app/db/database_maintenance.py:70`, `app/db/database_maintenance.py:88`, `app/db/database_maintenance.py:117`, `app/db/database_maintenance.py:159`, `app/db/database_maintenance.py:164`, and `app/db/database_maintenance.py:169` issue SQLite maintenance PRAGMAs/commands; replace with Postgres-specific maintenance or no-op startup behavior in R1/O2. |
| replace | `app/db/health_check.py:91`, `app/db/health_check.py:109`, and `app/db/health_check.py:276` use direct SQL/PRAGMA health checks; replace with Postgres checks. |
| replace | `app/cli/add_performance_indexes.py:85`, `app/cli/add_performance_indexes.py:108`, and `app/cli/add_performance_indexes.py:119` use SQLite index DDL/introspection; replace with Alembic/SQLAlchemy inspector or delete if superseded by the baseline. |
| delete | `app/cli/migrations/001_add_performance_indexes.py:151` and `app/cli/migrations/001_add_performance_indexes.py:200` run legacy index DDL. |
| delete | `app/cli/migrations/002_add_schema_constraints.py:61` through `app/cli/migrations/002_add_schema_constraints.py:266` run legacy SQLite table rebuilds, trigger DDL, and cleanup SQL. |
| delete | `app/cli/migrations/007_add_attachment_processing.py:31`, `app/cli/migrations/007_add_attachment_processing.py:50`, `app/cli/migrations/007_add_attachment_processing.py:53`, and `app/cli/migrations/007_add_attachment_processing.py:67` run legacy table DDL. |
| delete | `app/cli/migrations/008_add_request_error_fields.py:34`, `app/cli/migrations/009_add_digest_indexes.py:67`, `app/cli/migrations/009_add_digest_indexes.py:104`, `app/cli/migrations/010_add_request_error_context.py:30`, `app/cli/migrations/011_add_channel_metadata.py:36`, and `app/cli/migrations/013_add_reading_position.py:31` run deprecated migration SQL. |
| replace | `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:144`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:147`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:162`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:165`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:258`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:286`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:315`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:382`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:434`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:612`, and `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:626` are repository-owned raw SQL call sites; replace with SQLAlchemy in R2/M3. |
| replace | `app/infrastructure/persistence/sqlite/repositories/_summary_repo_shared.py:99` executes FTS5 search SQL; replace with the new topic search manager. |
| replace | `tests/stress/test_db_concurrency.py:47`, `tests/stress/test_db_concurrency.py:66`, `tests/stress/test_db_concurrency.py:79`, `tests/stress/test_db_concurrency.py:98`, `tests/stress/test_db_concurrency.py:109`, `tests/stress/test_db_concurrency.py:122`, `tests/stress/test_db_concurrency.py:135`, `tests/stress/test_db_concurrency.py:149`, `tests/stress/test_db_concurrency.py:175`, `tests/stress/test_db_concurrency.py:194`, `tests/stress/test_db_concurrency.py:213`, `tests/stress/test_db_concurrency.py:234`, `tests/stress/test_db_concurrency.py:252`, and `tests/stress/test_db_concurrency.py:267` are SQLite concurrency tests; replace with Postgres concurrency stress tests in T3. |
| replace | `tests/integration/test_phase2.py:100`, `tests/integration/test_phase2.py:115`, `tests/integration/test_phase2.py:132`, `tests/integration/test_phase2.py:139`, `tests/integration/test_phase2.py:158`, `tests/integration/test_phase2.py:177`, `tests/integration/test_phase2.py:183`, `tests/integration/test_phase2.py:203`, `tests/integration/test_phase2.py:211`, and `tests/integration/test_phase2.py:221` assert SQLite migration/schema behavior; replace with SQLAlchemy/Postgres schema tests in T3. |

## Pragmas

| Classification | Entry |
| --- | --- |
| replace | `app/di/database.py:115` runs `PRAGMA integrity_check`; replace with a Postgres connection/schema check. |
| replace | `app/db/alembic/env.py:48` through `app/db/alembic/env.py:51` set SQLite PRAGMAs; delete when Alembic env targets Postgres. |
| replace | `app/db/health_check.py:109` checks `PRAGMA foreign_keys`; Postgres enforces FKs, so this becomes a no-op success or a constraint catalog check. |
| replace | `app/db/health_check.py:276` checks `PRAGMA journal_mode`; replace with Postgres setting/connection diagnostics. |
| replace | `app/db/database_maintenance.py:117`, `app/db/database_maintenance.py:159`, `app/db/database_maintenance.py:164`, and `app/db/database_maintenance.py:169` inspect WAL/page/free-list PRAGMAs; replace with Postgres maintenance/statistics. |
| replace | `app/db/runtime/backup.py:34` runs `PRAGMA quick_check` on backup output; replace with `pg_restore --list` or restore-and-count validation. |
| replace | `app/db/runtime/inspection.py:29` runs `PRAGMA quick_check`; replace with `SELECT 1` plus Postgres catalog/stat checks. |
| keep-as-is | `app/adapters/digest/session_validator.py:44` runs `PRAGMA table_info(version)` against Telethon's session DB. This is explicitly out of migration scope because Telethon stores its own session in SQLite and does not support Postgres sessions. |
| keep-as-is | `tests/test_digest_session_validator.py:14`, `tests/test_digest_session_validator.py:32`, and `tests/test_digest_session_validator.py:48` exercise the Telethon SQLite session validator. |
| replace | `tests/test_user_digest_preference.py:101`, `tests/db/test_database_maintenance.py:61`, and related SQLite setup assertions should move to Postgres fixture setup or be deleted with the old maintenance service. |

## FTS5

| Classification | Entry |
| --- | --- |
| replace | `app/db/_models_core.py:6` imports `FTS5Model` and `SearchField`; replace with a SQLAlchemy model using PostgreSQL `TSVECTOR`. |
| replace | `app/db/_models_core.py:236` defines `TopicSearchIndex(FTS5Model)`. |
| replace | `app/db/topic_search_index.py:127` uses `MATCH`; `app/db/topic_search_index.py:128` orders by `bm25(topic_search_index)`; replace with `websearch_to_tsquery` and `ts_rank_cd`. |
| replace | `app/db/topic_search_index.py:238` uses the FTS5 `'delete-all'` control row; delete under Postgres. |
| replace | `app/infrastructure/persistence/sqlite/repositories/_summary_repo_shared.py:93` and `app/infrastructure/persistence/sqlite/repositories/_summary_repo_shared.py:94` use `MATCH` and `bm25`; route through the M3 manager. |
| replace | `app/api/routers/search.py:63` and `app/infrastructure/search/hybrid_search_service.py:35` describe FTS5 behavior; update documentation/comments to Postgres full-text search. |
| replace | `tests/test_topic_search_service.py:284` inspects SQLite FTS state; replace with the T3 topic-search regression fixture. |

## Alembic

| Classification | Entry |
| --- | --- |
| replace | `app/db/alembic_runner.py:11` imports `sqlite3`; `app/db/alembic_runner.py:30` builds a `sqlite:///` URL; rewrite around `DATABASE_URL` and Postgres. |
| replace | `app/db/alembic_runner.py:39`, `app/db/alembic_runner.py:41`, `app/db/alembic_runner.py:56`, `app/db/alembic_runner.py:58`, and `app/db/alembic_runner.py:73` use `sqlite3` and `sqlite_master`; replace during O5/M4. |
| replace | `app/db/alembic/env.py:38`, `app/db/alembic/env.py:42`, `app/db/alembic/env.py:43`, and `app/db/alembic/env.py:48` through `app/db/alembic/env.py:51` are SQLite-specific configuration and PRAGMAs. |
| delete | Existing SQLite revisions under `app/db/alembic/versions/` contain `sqlite_master`, `PRAGMA table_info`, `PRAGMA index_list`, SQLite triggers, and table-rebuild DDL, for example `app/db/alembic/versions/0003_002_add_schema_constraints.py:90`, `app/db/alembic/versions/0004_003_add_user_preferences.py:21`, `app/db/alembic/versions/0006_005_add_schema_columns.py:47`, `app/db/alembic/versions/0009_008_add_request_error_fields.py:29`, `app/db/alembic/versions/0013_012_add_channel_categories.py:41`, and `app/db/alembic/versions/0016_015_add_signal_sources.py:139`. M4 should replace this lineage with the reviewed PostgreSQL baseline. |
| delete | `app/cli/migrations/` is deprecated by `app/db/schema_migrator.py:6` through `app/db/schema_migrator.py:10` and must not be run. Remove the directory once the PostgreSQL baseline exists. |
| replace | `tests/db/test_alembic_runner.py:14`, `tests/db/test_alembic_runner.py:57`, `tests/db/test_alembic_runner.py:82`, `tests/db/test_alembic_runner.py:152`, `tests/db/test_alembic_runner.py:164`, and `tests/db/test_alembic_runner.py:185` are SQLite Alembic runner tests; replace with Postgres Alembic tests. |

## Healthchecks

| Classification | Entry |
| --- | --- |
| replace | `ops/docker/docker-compose.yml:58` healthchecks the bot with `sqlite3.connect(os.getenv('DB_PATH', '/data/ratatoskr.db'))`; replace with `python -m app.cli.healthcheck` against `DATABASE_URL`. |
| replace | `ops/docker/Dockerfile:118` through `ops/docker/Dockerfile:120` run a SQLite healthcheck; replace with the same Postgres-aware CLI healthcheck or remove in favor of compose healthchecks. |
| replace | `ops/docker/Dockerfile:24`, `ops/docker/Dockerfile:74`, `ops/docker/Dockerfile.api:20`, and `ops/docker/Dockerfile.api:58` install SQLite client/runtime packages; reassess after L2. The migrator may temporarily need SQLite libraries until Peewee removal. |
| replace | `app/api/routers/health.py:87` offloads `_compute_database_details` to a thread because current DB APIs are sync; replace with async DB checks. |
| replace | `app/api/services/system_maintenance_service.py:48`, `app/api/services/system_maintenance_service.py:101`, `app/api/services/system_maintenance_service.py:104`, `app/api/services/system_maintenance_service.py:183`, and `app/api/services/system_maintenance_service.py:184` expose/backup raw SQLite files; replace with `pg_dump`-based backup and Postgres table inspection. |

## Peewee Imports

All `app/` Peewee imports are migration targets except the temporary legacy migrator snapshot that T2 will add under `app/cli/_legacy_peewee_models/`.

| Classification | Entry |
| --- | --- |
| replace | Core DB/runtime modules: `app/db/_models_base.py:8`, `app/db/session.py:11`, `app/db/session.py:18`, `app/db/runtime/operation_executor.py:8`, `app/db/runtime/bootstrap.py:11`, `app/db/runtime/inspection.py:12`, `app/db/schema_migrator.py:25`, `app/db/health_check.py:17`, `app/db/database_diagnostics.py:8`, `app/db/database_diagnostics.py:9`, `app/db/database_maintenance.py:12`, `app/db/database_maintenance.py:19`, `app/db/batch_operations.py:14`, and `app/db/topic_search_index.py:10`. |
| replace | Model modules: `app/db/_models_core.py:5`, `app/db/_models_aggregation.py:5`, `app/db/_models_batch.py:5`, `app/db/_models_collections.py:5`, `app/db/_models_digest.py:5`, `app/db/_models_rss.py:5`, `app/db/_models_rules.py:5`, `app/db/_models_signal.py:5`, and `app/db/_models_user_content.py:5`. |
| replace | DI/API services: `app/di/database.py:10`, `app/di/database.py:141`, `app/api/main.py:14`, `app/api/services/_digest_api_channels.py:7`, `app/api/services/_digest_api_categories.py:7`, and `app/api/services/system_maintenance_service.py:14`. |
| replace | Telegram/messaging/rules call sites: `app/adapters/telegram/command_handlers/digest_handler.py:8`, `app/infrastructure/messaging/handlers/smart_collection_handler.py:7`, and `app/infrastructure/rules/collection_membership.py:5`. |
| replace | Persistence repositories: `app/infrastructure/persistence/sqlite/repositories/telegram_message_repository.py:12`, `app/infrastructure/persistence/sqlite/repositories/telegram_message_repository.py:129`, `app/infrastructure/persistence/sqlite/repositories/telegram_message_repository.py:181`, `app/infrastructure/persistence/sqlite/repositories/_summary_repo_reads.py:7`, `app/infrastructure/persistence/sqlite/repositories/_summary_repo_sync.py:7`, `app/infrastructure/persistence/sqlite/repositories/_collection_repo_items.py:7`, `app/infrastructure/persistence/sqlite/repositories/topic_search_repository.py:13`, `app/infrastructure/persistence/sqlite/repositories/crawl_result_repository.py:10`, `app/infrastructure/persistence/sqlite/repositories/crawl_result_repository.py:82`, `app/infrastructure/persistence/sqlite/repositories/crawl_result_repository.py:104`, `app/infrastructure/persistence/sqlite/repositories/tag_repository.py:11`, `app/infrastructure/persistence/sqlite/repositories/_request_repo_writes.py:7`, `app/infrastructure/persistence/sqlite/repositories/signal_source_repository.py:8`, `app/infrastructure/persistence/sqlite/repositories/_joined_row_utils.py:10`, `app/infrastructure/persistence/sqlite/repositories/_request_repo_telegram.py:7`, `app/infrastructure/persistence/sqlite/repositories/embedding_repository.py:11`, `app/infrastructure/persistence/sqlite/repositories/batch_session_repository.py:11`, `app/infrastructure/persistence/sqlite/repositories/user_repository.py:11`, `app/infrastructure/persistence/sqlite/repositories/_request_repo_reads.py:7`, `app/infrastructure/persistence/sqlite/repositories/llm_repository.py:10`, `app/infrastructure/persistence/sqlite/repositories/llm_repository.py:156`, `app/infrastructure/persistence/sqlite/repositories/llm_repository.py:178`, `app/infrastructure/persistence/sqlite/repositories/admin_read_repository.py:7`, `app/infrastructure/persistence/sqlite/repositories/rss_feed_repository.py:11`, `app/infrastructure/persistence/sqlite/repositories/_summary_repo_shared.py:10`, and `app/infrastructure/persistence/sqlite/repositories/audio_generation_repository.py:7`. |
| replace | CLI/MCP call sites: `app/cli/backfill_embeddings.py:58`, `app/mcp/catalog_service.py:234`, and all direct ORM users in `app/mcp/article_service.py` and `app/mcp/catalog_service.py` found by `Model.select()`/`get_or_none()` scans. |
| delete | Deprecated migration scripts: `app/cli/migrations/001_add_performance_indexes.py:17`, `app/cli/migrations/003_add_user_preferences.py:15`, `app/cli/migrations/003_add_user_preferences.py:16`, `app/cli/migrations/005_add_schema_columns.py:27`, `app/cli/migrations/006_migrate_legacy_payloads.py:24`, `app/cli/migrations/006_migrate_legacy_payloads.py:25`, `app/cli/migrations/008_add_request_error_fields.py:13`, `app/cli/migrations/009_add_digest_indexes.py:13`, `app/cli/migrations/010_add_request_error_context.py:10`, `app/cli/migrations/011_add_channel_metadata.py:7`, `app/cli/migrations/012_add_channel_categories.py:7`, `app/cli/migrations/013_add_reading_position.py:12`, `app/cli/migrations/014_add_bot_reply_message_id.py:10`, and `app/cli/migrations/migration_runner.py:32`. |
| replace | Tests importing Peewee: `tests/db_helpers.py:14`, `tests/integration/test_channel_digest_scheduler.py:20`, `tests/integration/test_phase2.py:15`, `tests/test_user_digest_preference.py:13`, `tests/test_user_digest_preference.py:59`, `tests/api/test_request_status.py:3`, `tests/api/test_request_service_error_details.py:5`, `tests/test_digest_api_service.py:22`, `tests/test_digest_handler.py:10`, `tests/infrastructure/test_digest_signal_mirror.py:7`, `tests/infrastructure/test_request_repository_error_context.py:3`, `tests/infrastructure/test_summary_repository_finalize.py:3`, `tests/infrastructure/test_signal_source_repository.py:9`, `tests/infrastructure/test_summary_repository.py:7`, `tests/infrastructure/test_llm_repository_batch.py:3`, `tests/db/test_alembic_runner.py:53`, `tests/db/test_database_maintenance.py:7`, and `tests/test_mcp_context.py:15`. |
| keep-as-is | `tests/test_forward_summarizer.py:9` mocks `playhouse.sqlite_ext` only to isolate an import-time dependency. Delete once imports no longer require Playhouse. |

## asyncio.to_thread Callers

Only DB-compensation thread offloads are migration targets. CPU-bound or third-party sync library offloads are `keep-as-is` unless they also touch Peewee/SQLite.

| Classification | Entry |
| --- | --- |
| replace | `app/db/runtime/operation_executor.py:160`, `app/db/runtime/operation_executor.py:163`, and `app/db/runtime/operation_executor.py:193` wrap Peewee operations; delete with `AsyncRWLock` during F3/R1. |
| replace | `app/adapters/telegram/telegram_bot.py:378` offloads `self.db.create_backup_copy`; replace when backup becomes `pg_dump`/async runtime service. |
| replace | `app/adapters/telegram/summary_followup.py:144` offloads source context DB lookup; port with Telegram/application call sites. |
| replace | `app/adapters/telegram/callback_action_io_handlers.py:162`, `app/adapters/telegram/callback_action_store.py:48`, and `app/adapters/telegram/callback_action_store.py:97` offload callback store loaders; port with R3. |
| replace | `app/infrastructure/cache/trending_cache.py:138` offloads a Peewee summary query; port with repositories/cache integration. |
| replace | `app/application/services/signal_personalization.py:60` and `app/application/services/signal_personalization.py:111` offload persistence work; port with application call sites. |
| replace | `app/api/routers/health.py:87`, `app/api/routers/digest.py:39`, `app/api/routers/digest.py:50`, `app/api/routers/digest.py:63`, `app/api/routers/digest.py:158`, and `app/api/routers/digest.py:170` offload sync DB facade work; replace with async dependencies/services. |
| replace | `app/api/services/search_service.py:185` offloads search payload construction that currently reads through sync persistence; verify during R3. |
| replace | `tests/api/request_service_helpers.py:34`, `tests/api/request_service_helpers.py:51`, `tests/infrastructure/test_summary_repository.py:23`, `tests/infrastructure/test_summary_repository.py:26`, `tests/infrastructure/test_signal_source_repository.py:39`, `tests/infrastructure/test_signal_source_repository.py:42`, and `tests/test_session_cancellation.py:3` through `tests/test_session_cancellation.py:165` are test support for sync Peewee execution; replace/delete in T3. |
| keep-as-is | `app/adapters/twitter/playwright_client.py:3`, `app/adapters/twitter/playwright_client.py:394`, `app/adapters/twitter/playwright_client.py:411`, and `app/adapters/content/scraper/playwright_provider.py:141` wrap synchronous Playwright/ScrapeGraph work, not relational DB work. |
| keep-as-is | `app/adapters/youtube/session_service.py:91`, `app/adapters/youtube/youtube_downloader_parts/transcript_api.py:62`, `app/adapters/youtube/youtube_downloader_parts/transcript_api.py:124`, `app/adapters/youtube/download_pipeline.py:97`, `app/adapters/attachment/_attachment_content.py:375`, and `app/adapters/attachment/_attachment_content.py:484` wrap filesystem/media/third-party library calls. |
| keep-as-is | `app/infrastructure/messaging/handlers/embedding_generation.py:86`, `app/infrastructure/messaging/handlers/embedding_generation.py:96`, `app/infrastructure/messaging/handlers/embedding_generation.py:142`, `app/infrastructure/messaging/handlers/embedding_generation.py:157`, and `app/infrastructure/messaging/handlers/embedding_generation.py:160` wrap vector-store calls, not SQLite/Peewee. |
| keep-as-is | `app/infrastructure/embedding/embedding_service.py:85`, `app/infrastructure/embedding/embedding_service.py:119`, `app/infrastructure/embedding/gemini_embedding_service.py:71`, `app/infrastructure/embedding/gemini_embedding_service.py:98`, `app/infrastructure/audio/filesystem_storage.py:27`, `app/infrastructure/push/service.py:172`, `app/infrastructure/search/reranking_service.py:134`, `app/infrastructure/search/vector_search_service.py:111`, `app/infrastructure/search/vector_search_service.py:330`, `app/infrastructure/search/vector_topic_similarity.py:70`, `app/infrastructure/vector/qdrant_store.py:546`, `app/adapters/content/llm_response_workflow_attempts.py:75`, `app/adapters/content/llm_summarizer_semantic.py:108`, `app/adapters/content/scraper/scrapegraph_provider.py:108`, and `app/mcp/semantic_service.py:344` are non-relational offloads. |

## Tests

| Classification | Entry |
| --- | --- |
| replace | `tests/db_helpers.py:14`, `tests/db_helpers.py:29`, and the helper's `Model.create`/`Model.update`/`model_to_dict` calls such as `tests/db_helpers.py:58`, `tests/db_helpers.py:92`, `tests/db_helpers.py:112`, `tests/db_helpers.py:442`, and `tests/db_helpers.py:551` must be replaced with async SQLAlchemy fixtures/helpers. |
| replace | `tests/api/test_request_status.py:15`, `tests/api/test_request_service_error_details.py:17`, `tests/infrastructure/test_request_repository_error_context.py:18`, `tests/infrastructure/test_summary_repository.py:32`, `tests/infrastructure/test_summary_repository_finalize.py:18`, `tests/infrastructure/test_llm_repository_batch.py:18`, and `tests/infrastructure/test_signal_source_repository.py:48` create Peewee `SqliteDatabase` fixtures; replace with ephemeral Postgres fixtures. |
| replace | `tests/integration/test_phase2.py:60` creates a SQLite SQLAlchemy engine and `tests/integration/test_phase2.py:100` through `tests/integration/test_phase2.py:221` validate SQLite schema/triggers; replace with Postgres schema and migration tests. |
| replace | `tests/db/test_alembic_runner.py:14` through `tests/db/test_alembic_runner.py:185` are SQLite Alembic runner tests; replace with Postgres Alembic baseline tests. |
| replace | `tests/stress/test_db_concurrency.py:47` through `tests/stress/test_db_concurrency.py:267` exercise SQLite locking/pool behavior; replace with Postgres async concurrency tests, including dedupe-hash conflict stress. |
| keep-as-is | `tests/test_digest_session_validator.py:3`, `tests/test_digest_session_validator.py:14`, `tests/test_digest_session_validator.py:32`, and `tests/test_digest_session_validator.py:48` remain SQLite tests for Telethon session DB validation. |
| replace | API/system dump and maintenance tests using raw SQLite tables, including `tests/api/services/test_system_maintenance_service.py:48`, `tests/api/test_system_dump.py:107`, and `tests/api/test_user_stats.py:129`, should move to Postgres fixtures or pg_dump-oriented tests. |
| replace | MCP and domain tests using direct Peewee creates/selects, for example `tests/test_mcp_context.py:20`, `tests/test_mcp_resource_registrations.py:107`, `tests/domain/models/test_source.py:9`, and `tests/application/test_aggregation_dto.py:23`, must move to SQLAlchemy fixture factories. |

## Telethon Session Caveat

Telethon's session file is intentionally out of scope. `app/adapters/digest/session_validator.py:15` imports `sqlite3`, `app/adapters/digest/session_validator.py:43` opens the session file with `sqlite3.connect`, and `app/adapters/digest/session_validator.py:44` introspects the `version` table with `PRAGMA table_info(version)`. Keep this code and its tests because it validates Telethon's own SQLite session database, not Ratatoskr's relational store.

## Downstream Worklist Mapping

- F3 (`migrate-postgres-introduce-database-factory`): `app/db/session.py`, `app/di/database.py`, `app/config/settings.py`, `app/db/runtime/operation_executor.py`, and `app/db/rw_lock.py`.
- M1 (`migrate-postgres-port-models-core`): `app/db/_models_base.py`, `app/db/_models_core.py` except `TopicSearchIndex`.
- M2 (`migrate-postgres-port-models-features`): all feature `_models_*.py` files listed under Model Fields.
- M3 (`migrate-postgres-port-topic-search-model`): `app/db/_models_core.py:236`, `app/db/topic_search_index.py`, and FTS5 repository helpers.
- R1 (`migrate-postgres-port-runtime-services`): `app/db/runtime/`, `app/db/database_maintenance.py`, `app/db/database_diagnostics.py`, `app/db/health_check.py`.
- R2 (`migrate-postgres-port-persistence-repositories`): every file under `app/infrastructure/persistence/sqlite/` listed above.
- R3 (`migrate-postgres-port-application-call-sites`): direct ORM users under `app/api/`, `app/adapters/`, `app/application/`, `app/domain/`, `app/infrastructure/cache/`, `app/infrastructure/messaging/`, `app/infrastructure/rules/`, `app/mcp/`, and `app/cli/`.
- O2 (`migrate-postgres-port-raw-sql-helpers`): all non-Telethon `execute_sql`, `sqlite3.connect`, `sqlite_master`, and `PRAGMA` entries.
- T3 (`migrate-postgres-add-test-fixtures-and-ci`): all tests listed in the Tests section.
- L1/L2 (`migrate-postgres-remove-peewee`, `migrate-postgres-update-docs`): delete the temporary legacy Peewee snapshot after cutover and keep only the Telethon SQLite carve-out.

## Counts

These counts were captured on 2026-05-06 and are intended as reduction metrics during the R phase.

| Metric | Count |
| --- | ---: |
| Total Peewee import occurrences in `app/` and `tests/` | 92 |
| Total files with Peewee imports in `app/` and `tests/` | 80 |
| Total `asyncio.to_thread` / `_asyncio.to_thread` occurrences in `app/` and `tests/` | 61 |
| Total files with `asyncio.to_thread` / `_asyncio.to_thread` in `app/` and `tests/` | 33 |
| Total `execute_sql` occurrences in `app/`, `tests/`, and `ops/` | 124 |
| Total files with `execute_sql` in `app/`, `tests/`, and `ops/` | 33 |

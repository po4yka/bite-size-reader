# Rust Crate Guide

Per-crate reference for all 9 crates in the `rust/crates/` workspace.

## Inter-Crate Dependency Graph

```
bsr-models <-- bsr-persistence
bsr-pipeline-shadow <-- bsr-processing-orchestrator
(all others are independent leaf crates)
```

---

## bsr-config

**Purpose:** Environment configuration loading with validation. Provides `RuntimeConfig` (log level, DB path, concurrency limits) from env vars with defaults.

**Key deps:** serde, serde_json, thiserror

**Important types:**

- `RuntimeConfig { log_level, db_path, max_concurrent_calls }` -- loaded via `from_env()`
- `ConfigError::InvalidConcurrency` -- numeric parse failures

**CLI:** None

**Tests:** 1 unit test (`loads_defaults`)

**Notes:** Defaults: `LOG_LEVEL=INFO`, `DB_PATH=/data/app.db`, `MAX_CONCURRENT_CALLS=4`. No config files -- all via env.

---

## bsr-logging

**Purpose:** Structured JSON logging via tracing-subscriber. Idempotent initialization with env-based filters.

**Key deps:** tracing, tracing-subscriber

**Important types:**

- `init_logging(default_level: &str)` -- reads `RUST_LOG` env, falls back to provided default, then to "info"

**CLI:** None

**Tests:** 2 unit tests (idempotency, invalid level fallback)

**Notes:** Call is idempotent (safe to call multiple times). Outputs JSON format with target info.

---

## bsr-models

**Purpose:** Shared data structures for migrations and telemetry. Pure data containers, no business logic.

**Key deps:** serde, serde_json

**Important types:**

- `MigrationHistoryEntry { migration_name, applied_at, rollback_sql }`
- `MigrationStatusEntry { migration_name, applied, applied_at }`
- `MigrationStatusReport { total, applied, pending, migrations }`
- `TelemetryEvent { event_type, surface, correlation_id, metadata: BTreeMap }`

**CLI:** None

**Tests:** None (data-only crate)

**Notes:** Uses `BTreeMap` for consistent serialization order. Optional fields for flexible history tracking.

---

## bsr-persistence

**Purpose:** SQLite migration tracking and schema discovery. Maps repo migrations to applied history and detects schema mismatches.

**Key deps:** bsr-models, rusqlite, serde, serde_json, thiserror, tempfile (dev)

**Important types:**

- `PersistenceError { Sqlite, Io, MigrationsDirNotFound }`
- `open_connection(db_path)` -- opens SQLite connection
- `ensure_migration_history_table(conn)` -- creates migration_history table
- `list_applied_migrations(conn)` -- reads applied from DB
- `list_repo_migration_names(migrations_dir)` -- scans filesystem for `^\d{3}_.*\.py$` files
- `build_migration_status_report(repo, applied)` -- cross-references DB with repo
- `migration_status_report(db_path, migrations_dir)` -- full status check
- `find_repo_migrations_dir(start)` -- walks up to locate `app/cli/migrations`

**CLI:** None (used by Python CLI migration runner)

**Tests:** 6 unit tests using `tempfile::TempDir` for isolated DB and directory structures

**Notes:** Ancestral directory walking for repo root detection. Filename parsing via char iterator.

---

## bsr-summary-contract

**Purpose:** Validates, normalizes, and shapes summary JSON payloads. Backfills missing fields, enforces size limits, checks SQLite compatibility. **Largest crate (~2,171 lines).**

**Key deps:** rusqlite (bundled), serde, serde_json, thiserror

**Important types:**

- `SummaryValidationError { InvalidPayload, PayloadTooLarge }`
- `SqliteCompatibilityError { Sqlite, Json, IncompatibleSchema, RoundtripFailed }`
- `SqliteCompatibilityReport { compatible, missing_tables, missing_columns }`

**Key functions:**

- `validate_and_shape_summary(payload) -> Result<Value>` -- normalize field names, backfill 35+ fields, cap text lengths, extract keywords
- `check_sqlite_compatibility(db_path) -> Result<SqliteCompatibilityReport>` -- inspect schema
- `sqlite_roundtrip_smoke(db_path) -> Result<()>` -- transactional insert/read/rollback

**CLI subcommands:** `normalize`, `sqlite-check --db-path`, `sqlite-roundtrip --db-path`

**Tests:** 8+ unit tests using `tempfile::TempDir`

**Notes:** Extensive field normalization (camelCase/snake_case/aliases, 34+ mappings). Cascading backfill logic. Text capping with char boundary awareness (not byte truncation). Payload size limit: 100KB.

---

## bsr-pipeline-shadow

**Purpose:** Deterministic snapshots of Python processing pipeline slices. Models 8 steps (extraction -> chunking -> LLM planning -> synthesis) without executing actual services.

**Key deps:** serde, serde_json, thiserror, sha2, regex, once_cell

**Important types (inputs):**

- `ExtractionAdapterInput`, `ChunkingPreprocessInput`, `ChunkSentencePlanInput`
- `LlmWrapperPlanInput`, `ContentCleanerInput`, `SummaryAggregateInput`
- `ChunkSynthesisPromptInput`, `SummaryUserContentInput`

**Important types (outputs):**

- `ExtractionAdapterSnapshot` -- content fingerprint (SHA256), language hint, low-value flag
- `ChunkingPreprocessSnapshot` -- chunk_size (4K-12K), long_context_bypass
- `ChunkSentencePlanSnapshot` -- sentence-aligned chunks
- `LlmWrapperPlanSnapshot` -- retry chain with temperature presets
- Plus snapshots for cleaner, aggregate, synthesis, user_content

**Key functions:** 8 `build_*_snapshot()` builders + `clean_content_for_llm()`

**CLI subcommands:** `extraction-adapter`, `chunking-preprocess`, `chunk-sentence-plan`, `llm-wrapper-plan`, `content-cleaner`, `summary-aggregate`, `chunk-synthesis-prompt`, `summary-user-content`

**Tests:** 12+ unit tests (inline data)

**Notes:** Language detection via Unicode range (U+0400-U+04FF = Cyrillic). Lazy regex compilation via `once_cell::sync::Lazy`. All functions are pure (same input -> same output).

---

## bsr-interface-router

**Purpose:** Route request decisions for mobile API and Telegram commands. Maps HTTP paths to route keys with rate limit bucketing, and Telegram text to canonical commands.

**Key deps:** serde, serde_json

**Important types:**

- `MobileRouteInput { method, path }` / `MobileRouteDecision { route_key, rate_limit_bucket, requires_auth, handled }`
- `TelegramCommandInput { text }` / `TelegramCommandDecision { command, handled }`

**Key functions:**

- `resolve_mobile_route(input)` -- prefix matching with boundary checking (`/v1/summaries/123` matches but `/v1/summariesevil` does not)
- `resolve_telegram_command(input)` -- alias normalization, bot mention stripping (`/find@mybot` -> `/find`)

**CLI subcommands:** `mobile-route`, `telegram-command`

**Tests:** 80+ tests (10+ mobile routing, 70+ telegram commands)

**Notes:** Careful boundary checking (requires `/` or `?` after prefix). 19 canonical telegram commands with aliases. Case-sensitive matching.

---

## bsr-processing-orchestrator

**Purpose:** Orchestrates processing plans for URL and forward message flows. Decides chunking strategy, language, models, and LLM parameters.

**Key deps:** bsr-pipeline-shadow, serde, serde_json, thiserror

**Important types:**

- `UrlProcessingPlanInput` -- dedupe_hash, content, language, models, chunking config
- `UrlProcessingPlan` -- flow_kind, strategy ("chunked"/"single_pass"), chunk_plan, request_plan
- `ForwardProcessingPlanInput` -- text, source info, language, model
- `ForwardProcessingPlan` -- prompt assembly, truncation, token estimation

**Key functions:**

- `build_url_processing_plan(input)` -- language selection, model routing (Gemini special case for large content), chunking decision
- `build_forward_processing_plan(input)` -- source label, prompt formatting, truncation at 45K chars

**CLI subcommands:** `url-plan`, `forward-plan`

**Tests:** 3 unit tests (inline data)

**Notes:** Constants: `MAX_SINGLE_PASS_CHARS=50000`, `MAX_FORWARD_CONTENT_CHARS=45000`. Model context estimation per vendor (Gemini 2.5 -> 3M tokens *4* 0.75). Depends on bsr-pipeline-shadow for snapshot builders.

---

## bsr-telegram-runtime

**Purpose:** Telegram command routing and normalization. Maps raw user text to canonical command names, handling aliases, bot mentions, and case sensitivity.

**Key deps:** serde, serde_json

**Important types:**

- `TelegramCommandRouteInput { text }`
- `TelegramCommandRouteDecision { command, handled }`

**Key functions:**

- `resolve_command_route(input)` -- case-sensitive matching, `/` prefix required, bot mention stripping, alias normalization

**CLI:** None

**Tests:** 78 unit tests (exhaustive coverage of aliases, mentions, edge cases)

**Notes:** Overlaps with bsr-interface-router's telegram routing (separate crate for runtime vs interface layer concerns). `strip_bot_mention()` helper handles `@` suffix extraction.

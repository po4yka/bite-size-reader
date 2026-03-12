# Rust Workspace (M1-M6)

This workspace contains migration crates delivered across milestones **M1–M6**.

## Crates

- `bsr-config`: runtime configuration loading from environment variables
- `bsr-logging`: structured logging bootstrap (`tracing` + JSON formatter)
- `bsr-models`: shared Rust-side migration and telemetry model foundation
- `bsr-persistence`: SQLite migration-history/status plus processing-critical request/summary/llm/crawl CRUD
- `bsr-processing-orchestrator`: Rust-authoritative URL/forward execution bridge with NDJSON event streaming, extraction, cache, worker orchestration, and processing-path persistence
- `bsr-summary-contract`: summary contract validation/normalization + SQLite compatibility checks + CLI
- `bsr-worker`: Rust OpenRouter execution path for single-pass URL (text and multimodal), chunked URL, and forwarded-text summaries
- `bsr-pipeline-shadow`: M3 pipeline slice parity and runtime command surface
- `bsr-interface-router`: M4 mobile route + Telegram command routing surface
- `bsr-telegram-runtime`: M6-S1 Telegram command route-decision scaffold (`command-route`)

## Scope

- Production defaults are Rust-first for migrated slices.
- `SUMMARY_CONTRACT_BACKEND` and `MIGRATION_INTERFACE_BACKEND` require Rust.
- `MIGRATION_SHADOW_MODE_ENABLED` must remain enabled (M3 disabled mode is decommissioned).
- M6 Telegram command-route execution is Rust-authoritative.
- `MIGRATION_PROCESSING_ORCHESTRATOR_BACKEND=rust` makes Rust authoritative for URL and forwarded-text processing hot paths; Python remains the Telegram/progress/message-shell bridge.
- `MIGRATION_WORKER_BACKEND=rust` is now a secondary/test-only toggle when the processing orchestrator backend is Rust.
- Specialized Twitter/YouTube extraction paths and web-search enrichment are still outside the Rust processing cutover.
- Legacy `MIGRATION_TELEGRAM_RUNTIME_BACKEND` values are ignored with a warning.

## Recent Correctness Updates (2026-03-05)

- `bsr-summary-contract`
  - Unicode-safe `questions_answered` parsing for `Q:/A:` and `Question:/Answer:` text payloads.
  - Entity-array normalization ignores metadata-only objects (for example, `type`, `confidence`) unless an entity value is present.
- `bsr-pipeline-shadow`
  - Aggregation parser trims numeric strings before conversion (for example, `" 3 "` now parses as `3`).
- `bsr-interface-router`
  - Public endpoints accept query-string variants (`/health?probe=1`, `/metrics?x=1`, `/docs?x=1`, `/openapi.json?x=1`).
- `bsr-logging`
  - Logging bootstrap no longer panics on invalid env/default log levels; it falls back to `info`.

## Local checks

```bash
cargo check --workspace --manifest-path rust/Cargo.toml
cargo test --workspace --manifest-path rust/Cargo.toml
cargo test -p bsr-persistence -p bsr-processing-orchestrator --manifest-path rust/Cargo.toml

# Run milestone parity suites
bash scripts/migration/run_m2_parity_suite.sh
bash scripts/migration/run_m3_parity_suite.sh
bash scripts/migration/run_m4_parity_suite.sh
bash scripts/migration/run_m5_cutover_suite.sh
bash scripts/migration/run_processing_orchestrator_parity_suite.sh
bash scripts/migration/run_worker_chunked_parity_suite.sh
bash scripts/migration/run_m6_telegram_runtime_suite.sh
```

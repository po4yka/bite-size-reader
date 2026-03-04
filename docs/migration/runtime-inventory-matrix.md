# Runtime Inventory Matrix (Python -> Rust)

This matrix is the migration planning source of truth for runtime ownership.
It maps active Python runtime surfaces to Rust targets, current verification
coverage, and rollback controls.

## Status Legend

- `rust-authoritative`: production requests execute the Rust path for this slice.
- `python-owned`: production behavior still depends on Python execution here.
- `planned`: target crate/bin and parity coverage are defined but not implemented.

## Runtime Ownership Matrix

| Runtime surface | Python owner modules | Rust target crate/bin | Status | Parity / verification | Rollback switch |
| --- | --- | --- | --- | --- | --- |
| M2 summary contract shaping | `app/core/summary_contract.py`, `app/core/summary_contract_impl/rust_backend.py` | `rust/crates/bsr-summary-contract` (`bsr-summary-contract`) | `rust-authoritative` | `bash scripts/migration/run_m2_parity_suite.sh` | `SUMMARY_CONTRACT_BACKEND` (Rust required; non-rust values ignored) |
| M3 pipeline transform slices | `app/migration/pipeline_shadow.py`, `app/adapters/content/url_processor.py`, `app/adapters/content/llm_summarizer.py` | `rust/crates/bsr-pipeline-shadow` (`bsr-pipeline-shadow`) | `rust-authoritative` | `bash scripts/migration/run_m3_parity_suite.sh` | `MIGRATION_SHADOW_MODE_ENABLED` (must stay `true`) |
| M4 interface command/route selection | `app/migration/interface_router.py`, `app/api/middleware.py`, `app/adapters/telegram/message_router.py` | `rust/crates/bsr-interface-router` (`bsr-interface-router`) | `rust-authoritative` | `bash scripts/migration/run_m4_parity_suite.sh` | `MIGRATION_INTERFACE_BACKEND` (Rust required; non-rust values ignored) |
| Telegram bot orchestration and command lifecycle | `bot.py`, `app/adapters/telegram/*`, `app/handlers/*` | `rust/crates/bsr-telegram-runtime` + `rust/bin/bsr-bot` | `python-owned` | Gap: add Telegram command behavior parity suite for Rust runner | Planned: `MIGRATION_TELEGRAM_RUNTIME_BACKEND` (`python`/`rust`) during rollout |
| URL/forward summarization orchestration (network + pipeline composition) | `app/adapters/content/url_processor.py`, `app/adapters/content/llm_summarizer.py`, `app/adapters/telegram/forward_processor.py` | `rust/crates/bsr-processing-orchestrator` + `rust/bin/bsr-worker` | `python-owned` | Gap: add end-to-end orchestration parity pack (URL + forwarded content) | Planned: `MIGRATION_PROCESSING_ORCHESTRATOR_BACKEND` |
| Mobile API request execution and background processing | `app/api/main.py`, `app/api/routers/*`, `app/api/background_processor.py`, `app/api/services/*` | `rust/crates/bsr-mobile-api` + `rust/bin/bsr-api` | `python-owned` | Existing API tests are Python-runtime only; add cross-runtime response parity harness | Planned: `MIGRATION_API_RUNTIME_BACKEND` |
| Persistence/service orchestration (SQLite access + write paths) | `app/db/*`, `app/infrastructure/persistence/*`, `app/services/*` | `rust/crates/bsr-persistence` | `python-owned` | M2 covers schema compatibility only; add CRUD parity against production snapshots | Planned: `MIGRATION_PERSISTENCE_BACKEND` |
| Operational interfaces (MCP + gRPC servers) | `app/mcp/server.py`, `app/grpc/server.py`, `app/grpc/service.py` | `rust/crates/bsr-interop-gateway` + `rust/bin/bsr-interop` | `python-owned` | Gap: protocol-level parity tests for MCP and gRPC handlers | Planned: `MIGRATION_INTEROP_BACKEND` |

## Recommended Execution Order for Remaining Python-Owned Surfaces

1. Telegram orchestration runtime (`bsr-telegram-runtime`) to remove Python from command lifecycle.
2. Mobile API runtime (`bsr-mobile-api`) with response-envelope parity validation.
3. Processing orchestrator (`bsr-processing-orchestrator`) for URL/forward flow composition.
4. Persistence crate (`bsr-persistence`) once read/write parity tests are in place.
5. MCP/gRPC interop gateway (`bsr-interop-gateway`) after core runtime cutover.

## Verification Baseline Before and After Each Slice

Run all required migration suites at each slice boundary:

- `cargo check --workspace --manifest-path rust/Cargo.toml`
- `cargo test --workspace --manifest-path rust/Cargo.toml`
- `bash scripts/migration/run_m2_parity_suite.sh`
- `bash scripts/migration/run_m3_parity_suite.sh`
- `bash scripts/migration/run_m4_parity_suite.sh`
- `bash scripts/migration/run_m5_cutover_suite.sh`
- `uv run bash scripts/migration/run_parity_suite.sh`

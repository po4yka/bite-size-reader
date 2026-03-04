# Rust Workspace (M1-M6)

This workspace contains migration crates delivered across milestones **M1–M6**.

## Crates

- `bsr-config`: runtime configuration loading from environment variables
- `bsr-logging`: structured logging bootstrap (`tracing` + JSON formatter)
- `bsr-summary-contract`: summary contract validation/normalization + SQLite compatibility checks + CLI
- `bsr-pipeline-shadow`: M3 pipeline slice parity and runtime command surface
- `bsr-interface-router`: M4 mobile route + Telegram command routing surface
- `bsr-telegram-runtime`: M6-S1 Telegram command route-decision scaffold (`command-route`)

## Scope

- Production defaults are Rust-first for migrated slices.
- `SUMMARY_CONTRACT_BACKEND` and `MIGRATION_INTERFACE_BACKEND` require Rust.
- `MIGRATION_SHADOW_MODE_ENABLED` must remain enabled (M3 disabled mode is decommissioned).
- M6 Telegram command-route execution is Rust-authoritative.
- Legacy `MIGRATION_TELEGRAM_RUNTIME_BACKEND` values are ignored with a warning.

## Local checks

```bash
cargo check --workspace --manifest-path rust/Cargo.toml
cargo test --workspace --manifest-path rust/Cargo.toml

# Run milestone parity suites
bash scripts/migration/run_m2_parity_suite.sh
bash scripts/migration/run_m3_parity_suite.sh
bash scripts/migration/run_m4_parity_suite.sh
bash scripts/migration/run_m5_cutover_suite.sh
bash scripts/migration/run_m6_telegram_runtime_suite.sh
```

# Rust Workspace (M1-M2)

This workspace contains shared crates introduced during migration milestones **M1** and **M2**.

## Crates

- `bsr-config`: runtime configuration loading from environment variables
- `bsr-logging`: structured logging bootstrap (`tracing` + JSON formatter)
- `bsr-summary-contract`: summary contract validation/normalization + SQLite compatibility checks + CLI

## Scope

- Python remains the production orchestrator by default.
- Summary contract backend can be switched using `SUMMARY_CONTRACT_BACKEND` (`python`/`auto`/`rust`).

## Local checks

```bash
cargo check --workspace --manifest-path rust/Cargo.toml
cargo test --workspace --manifest-path rust/Cargo.toml

# Run M2 contract + sqlite parity suite only
bash scripts/migration/run_m2_parity_suite.sh
```

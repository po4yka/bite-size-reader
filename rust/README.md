# Rust Workspace (M1 Foundation)

This workspace contains non-critical shared crates introduced in migration milestone **M1**.

## Crates

- `bsr-config`: runtime configuration loading from environment variables
- `bsr-logging`: structured logging bootstrap (`tracing` + JSON formatter)
- `bsr-summary-contract`: summary contract validation primitives

## Scope

- Python remains the production orchestrator.
- These crates are intentionally small and isolated to support incremental adoption in M2+.

## Local checks

```bash
cargo check --workspace --manifest-path rust/Cargo.toml
cargo test --workspace --manifest-path rust/Cargo.toml
```

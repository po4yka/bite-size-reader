---
name: writing-rust-code
description: >
  Write, test, debug, and maintain Rust code in the bite-size-reader workspace.
  Covers all 9 crates, migration parity testing, and coding conventions.
  Trigger keywords: rust, cargo, crate, migration, parity, bsr-, rustc,
  clippy, cargo test, cargo check, Cargo.toml, thiserror, serde, rusqlite.
version: 1.0.0
allowed-tools: Bash, Read, Grep, Write, Edit
---

# Writing Rust Code

Write, test, debug, and maintain Rust code in the bite-size-reader workspace.

## Dynamic Context

```bash
!bash .claude/skills/writing-rust-code/scripts/rust-check.sh 2>/dev/null || echo "Rust workspace: check failed"
```

```bash
!git log --oneline -5 -- rust/
```

```bash
!git diff --stat HEAD -- rust/
```

## Workspace Layout

- **Root manifest:** `rust/Cargo.toml`
- **Edition:** 2021, resolver 2
- **9 crates** in `rust/crates/`:
  - `bsr-config` -- env-based configuration
  - `bsr-logging` -- structured JSON logging (tracing)
  - `bsr-models` -- shared data types (migrations, telemetry)
  - `bsr-persistence` -- SQLite migration tracking (depends on bsr-models)
  - `bsr-summary-contract` -- summary JSON validation/normalization (~2K lines)
  - `bsr-pipeline-shadow` -- 8 deterministic pipeline snapshot builders
  - `bsr-interface-router` -- mobile API + telegram command routing
  - `bsr-processing-orchestrator` -- URL/forward plan assembly (depends on bsr-pipeline-shadow)
  - `bsr-telegram-runtime` -- telegram command normalization
- **Detailed crate docs:** [references/crate-guide.md](references/crate-guide.md)

## Core Workflows

### Writing Code

1. Read the relevant crate's `lib.rs` and `Cargo.toml` first
2. Follow existing patterns -- check [references/crate-guide.md](references/crate-guide.md) for each crate's conventions
3. Use `*Input` / `*Output` (or `*Snapshot`, `*Decision`, `*Plan`) naming for typed boundaries
4. All public types derive `Serialize, Deserialize`
5. Use `thiserror` for error enums, `serde_json::Value` for flexible payloads

### Running Checks

```bash
# Type check (fast, no codegen)
cargo check --workspace --manifest-path rust/Cargo.toml

# Lint
cargo clippy --all-targets --manifest-path rust/Cargo.toml

# Format
cargo fmt --all --manifest-path rust/Cargo.toml
cargo fmt --check --manifest-path rust/Cargo.toml
```

### Testing

```bash
# All workspace tests
cargo test --workspace --manifest-path rust/Cargo.toml

# Single crate
cargo test -p bsr-summary-contract --manifest-path rust/Cargo.toml

# Specific test with output
cargo test -p bsr-interface-router mobile_route -- --nocapture

# List tests
cargo test --workspace --manifest-path rust/Cargo.toml -- --list
```

### Adding a New Crate

```bash
cargo init --lib rust/crates/bsr-{name}
```

Then:

1. Add `"crates/bsr-{name}"` to workspace members in `rust/Cargo.toml`
2. Use workspace deps: `serde = { workspace = true }` in the crate's `Cargo.toml`
3. Set `edition.workspace = true`, `version.workspace = true`, `license.workspace = true`

### Building CLI Binaries

```bash
# Build all binaries (release)
cargo build --release --bins --manifest-path rust/Cargo.toml

# Build specific binary
cargo build --release -p bsr-pipeline-shadow --manifest-path rust/Cargo.toml

# Run a binary with JSON stdin
echo '{"url_hash":"abc","content_text":"Hello world"}' | cargo run -p bsr-pipeline-shadow --manifest-path rust/Cargo.toml -- extraction-adapter
```

### Debugging

```bash
# Verbose test output
RUST_LOG=debug cargo test --workspace --manifest-path rust/Cargo.toml -- --nocapture

# Run specific parity test
cargo test -p bsr-summary-contract --test m2_fixture_parity --manifest-path rust/Cargo.toml
```

## Coding Conventions

### Error Handling

- Use `thiserror` for all error enums
- Wrap external errors: `#[error(transparent)] Sqlite(#[from] rusqlite::Error)`
- Use `?` operator throughout; no panics in library code
- CLI `main.rs`: print error to stderr + `std::process::exit(1)`

### Serde Patterns

- All public types: `#[derive(Debug, Clone, Serialize, Deserialize)]`
- Use `#[serde(default)]` for optional/backfill fields
- Use `BTreeMap` (not `HashMap`) for consistent JSON field ordering
- Use `serde_json::Value` for flexible schema payloads

### Type Design

- Input structs: `*Input` suffix (e.g., `ExtractionAdapterInput`)
- Output structs: `*Snapshot`, `*Decision`, `*Plan`, `*Report` suffix
- Keep types in `lib.rs` unless the crate grows large enough to warrant modules
- Frozen dataclass equivalent: all fields public, derive Clone

### Test Patterns

- Unit tests in `#[cfg(test)] mod tests` at bottom of `lib.rs`
- Parity tests in `tests/m{N}_fixture_parity.rs` (integration test files)
- Use `tempfile::TempDir` for isolated DB/filesystem tests (add `tempfile` to `[dev-dependencies]`)
- Inline test data preferred over external fixture files for unit tests
- Test naming: `fn {function_name}_{behavior_under_test}()`

### Dependencies

- Always use workspace deps from `rust/Cargo.toml [workspace.dependencies]`
- Available: serde, serde_json, thiserror, tokio, tracing, tracing-subscriber, rusqlite (bundled), axum, reqwest, tonic, grammers-client
- Add new workspace deps to `rust/Cargo.toml` before referencing in crates

## Migration Workflow

See [references/migration-workflow.md](references/migration-workflow.md) for the full migration guide including:

- M0-M6 milestone details
- Fixture-based parity testing workflow
- JSON IPC contract specification
- 10-step checklist for adding new migration steps

**Key points:**

- All migrated slices (M2-M6) are Rust-authoritative
- Python bridges call Rust via subprocess (JSON stdin/stdout)
- Parity tests compare Rust output against Python-generated baselines
- CI enforces fixture freshness + Rust parity for every PR

## Key Files

| File | Purpose |
|------|---------|
| `rust/Cargo.toml` | Workspace manifest, shared deps |
| `rust/crates/bsr-summary-contract/src/lib.rs` | Largest crate, exemplifies conventions |
| `rust/crates/bsr-pipeline-shadow/src/main.rs` | Canonical CLI binary pattern |
| `rust/crates/bsr-pipeline-shadow/src/lib.rs` | Snapshot types and computation |
| `rust/crates/bsr-processing-orchestrator/src/lib.rs` | Composition pattern (uses bsr-pipeline-shadow) |
| `docs/migration/m2.md` | Most complete milestone doc (fixture testing, backend selection) |
| `scripts/migration/generate_m2_contract_fixtures.py` | Baseline generation example |

## Common Pitfalls

1. **No config files** -- all configuration via environment variables (`RuntimeConfig::from_env()`), never read from files
2. **No pre-commit hooks for Rust** -- run `cargo fmt` and `cargo clippy` manually before committing Rust changes
3. **Workspace deps required** -- never add deps directly to a crate's `[dependencies]`; add to `rust/Cargo.toml [workspace.dependencies]` first, then reference with `{ workspace = true }`
4. **Bundled rusqlite** -- the workspace uses `rusqlite = { version = "0.32", features = ["bundled"] }` to avoid system SQLite dependency issues
5. **JSON IPC pattern** -- CLI binaries read JSON from stdin, write JSON to stdout, errors to stderr with exit code 1. Never write non-JSON to stdout
6. **Crate role boundaries** -- bsr-interface-router handles routing decisions, bsr-telegram-runtime handles command normalization. Don't mix concerns
7. **Fixture `project_root()`** -- parity test files use path resolution relative to `CARGO_MANIFEST_DIR` to find `docs/migration/fixtures/`. Use `PathBuf::from(env!("CARGO_MANIFEST_DIR"))` and walk up to repo root

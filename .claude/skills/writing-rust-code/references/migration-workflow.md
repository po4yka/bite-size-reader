# Rust Migration Workflow

## Milestone Overview

| Milestone | Focus | Rust-Authoritative | Status |
|-----------|-------|-------------------|--------|
| M0-M1 | Foundation (workspace setup, initial crates) | No | Complete |
| M2 | Data & Contract Layer (summary validation, SQLite compat) | Yes | Complete |
| M3 | Processing Pipeline (8 pipeline shadow slices) | Yes | Complete |
| M4 | Interface Layer (mobile API routing, telegram commands) | Yes | Complete |
| M5 | Cutover & Decommission (production defaults, Python fallback removal) | Yes (enforced) | Complete |
| M6 | Processing Orchestrator (URL/forward plan assembly) | Yes | Complete |

### What Each Milestone Migrated

**M2 -- Summary Contract:** `validate_and_shape_summary()`, `check_sqlite_compatibility()`, `sqlite_roundtrip_smoke()`. Crate: `bsr-summary-contract`. Python bridge: `app/core/summary_contract_impl/rust_backend.py`.

**M3 -- Pipeline Shadow:** 8 deterministic snapshot builders (extraction_adapter, chunking_preprocess, chunk_sentence_plan, llm_wrapper_plan, content_cleaner, summary_aggregate, chunk_synthesis_prompt, summary_user_content). Crate: `bsr-pipeline-shadow`. Python bridge: `app/migration/pipeline_shadow.py`.

**M4 -- Interface Router:** Mobile API route classification and Telegram command routing. Crate: `bsr-interface-router`. Python bridge: `app/migration/interface_router.py`.

**M5 -- Cutover:** Production defaults set to `rust` for M2 and M4. Cutover event monitoring for operational visibility. No Python fallback.

**M6 -- Processing Orchestrator:** URL and forward message processing plan assembly. Crate: `bsr-processing-orchestrator`. Composes bsr-pipeline-shadow snapshot builders.

---

## Fixture-Based Parity Testing

### Fixture Directory Structure

```
docs/migration/fixtures/
  m2_summary_contract/
    input/*.json          -- Raw fixture payloads
    expected/*.json       -- Python-generated baselines
    README.md
  m3_pipeline_shadow/
    input/*.json          -- Per-slice fixture payloads
    expected/*.json       -- Expected snapshot outputs
    README.md
  m4_interface_routing/
    input/*.json          -- Route/command test cases
    expected/*.json       -- Expected routing decisions
    README.md
```

### Python Baseline Generation

Each milestone has a generator script that runs the Python reference implementation and writes expected outputs:

```bash
# M2: Summary contract baselines
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m2_contract_fixtures.py

# M3: Pipeline shadow baselines
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m3_shadow_fixtures.py

# M4: Interface routing baselines
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m4_interface_fixtures.py

# Check mode (CI -- verifies baselines are fresh, no writes)
PYTHONPATH=. .venv/bin/python scripts/migration/generate_m{N}_{name}_fixtures.py --check
```

### Rust Parity Tests

Each crate has a parity test file that loads fixtures, runs Rust logic, and compares against expected baselines:

| Milestone | Test File |
|-----------|-----------|
| M2 | `rust/crates/bsr-summary-contract/tests/m2_fixture_parity.rs` |
| M3 | `rust/crates/bsr-pipeline-shadow/tests/m3_fixture_parity.rs` |
| M4 | `rust/crates/bsr-interface-router/tests/m4_fixture_parity.rs` |

### Running Parity Suites

```bash
# Individual milestone suites
bash scripts/migration/run_m2_parity_suite.sh
bash scripts/migration/run_m3_parity_suite.sh
bash scripts/migration/run_m4_parity_suite.sh
bash scripts/migration/run_m5_cutover_suite.sh

# Full parity suite
uv run bash scripts/migration/run_parity_suite.sh
```

---

## JSON IPC Contract

All Rust CLI binaries follow the same IPC pattern for Python interop:

### Protocol

- **Input:** JSON on stdin
- **Output:** Pretty-printed JSON on stdout
- **Errors:** Message on stderr, exit code 1
- **Subcommands:** First positional argument selects the operation

### Per-Binary Subcommands

**bsr-summary-contract:**

```bash
bsr-summary-contract normalize < input.json
bsr-summary-contract sqlite-check --db-path /path/to/app.db
bsr-summary-contract sqlite-roundtrip --db-path /path/to/app.db
```

**bsr-pipeline-shadow:**

```bash
bsr-pipeline-shadow extraction-adapter < input.json
bsr-pipeline-shadow chunking-preprocess < input.json
bsr-pipeline-shadow chunk-sentence-plan < input.json
bsr-pipeline-shadow llm-wrapper-plan < input.json
bsr-pipeline-shadow content-cleaner < input.json
bsr-pipeline-shadow summary-aggregate < input.json
bsr-pipeline-shadow chunk-synthesis-prompt < input.json
bsr-pipeline-shadow summary-user-content < input.json
```

**bsr-processing-orchestrator:**

```bash
bsr-processing-orchestrator url-plan < input.json
bsr-processing-orchestrator forward-plan < input.json
```

**bsr-interface-router:**

```bash
bsr-interface-router mobile-route < input.json
bsr-interface-router telegram-command < input.json
```

### Binary Path Configuration

Python bridges locate Rust binaries via env vars (optional overrides):

```bash
SUMMARY_CONTRACT_RUST_BIN=/abs/path/to/bsr-summary-contract
PIPELINE_SHADOW_RUST_BIN=/abs/path/to/bsr-pipeline-shadow
INTERFACE_ROUTER_RUST_BIN=/abs/path/to/bsr-interface-router
```

### Runtime Configuration

```bash
# M2: Summary contract backend
SUMMARY_CONTRACT_BACKEND=rust     # canonical (legacy: auto/python ignored)

# M3: Pipeline shadow mode
MIGRATION_SHADOW_MODE_ENABLED=true
MIGRATION_SHADOW_MODE_TIMEOUT_MS=250

# M4: Interface routing backend
MIGRATION_INTERFACE_BACKEND=rust  # canonical (legacy: canary/python decommissioned)
MIGRATION_INTERFACE_TIMEOUT_MS=150
```

---

## How to Add a New Migration Step

1. **Define the slice boundary** -- identify the Python logic to migrate, document input/output types and edge cases

2. **Create the Rust crate:**

   ```bash
   cargo init --lib rust/crates/bsr-{name}
   ```

   Add to `rust/Cargo.toml` workspace members. Use workspace deps.

3. **Implement `lib.rs`** -- typed `*Input`/`*Output` structs with `#[derive(Serialize, Deserialize)]`, pure functions, unit tests

4. **Implement `main.rs`** -- CLI binary with subcommand dispatch, JSON stdin/stdout, stderr errors, exit code 1 on failure

5. **Create Python bridge** -- `app/migration/{name}.py` with frozen dataclasses, `build_python_*()` reference implementations, subprocess invocation

6. **Create fixture inputs** -- `docs/migration/fixtures/m{N}_{name}/input/*.json`

7. **Write fixture generator** -- `scripts/migration/generate_m{N}_{name}_fixtures.py` with `--check` flag for CI

8. **Generate baselines** -- run generator to populate `expected/*.json`

9. **Write Rust parity tests** -- `rust/crates/bsr-{name}/tests/m{N}_fixture_parity.rs`, load fixtures, compare against expected

10. **Add CI job** -- create `scripts/migration/run_m{N}_parity_suite.sh`, add job to `.github/workflows/ci.yml` with fixture freshness check + Rust parity tests

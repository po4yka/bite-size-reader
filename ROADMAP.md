# Roadmap: Python → Rust Migration

This roadmap tracks the project-wide migration from the current Python runtime to a Rust-first runtime while preserving API and bot behavior.

## Migration Goals

- Preserve existing user workflows (`/summarize`, `/search`, `/digest`, mobile API, MCP).
- Keep SQLite data compatible during and after migration.
- Ship in incremental slices with rollback points.
- Reduce memory footprint and improve throughput/latency in production.

## Current State

- **Production runtime:** Python (stable)
- **Target runtime:** Rust (incremental adoption)
- **Migration mode:** Strangler pattern (Rust services/modules replace Python components over time)

## Milestones

### M0 — Baseline and Contract Freeze ✅ Implemented

- Freeze external behavior contracts:
  - Telegram command semantics
  - Mobile API request/response models
  - Summary JSON contract
- Add parity test suite for API + end-to-end bot flows.
- Capture performance baseline (latency, memory, CPU, error rates).

**Exit criteria:** parity tests green on Python baseline, baseline metrics recorded.

### M1 — Rust Foundation (Non-Critical Path) ✅ Implemented

- Introduce Rust workspace and CI jobs.
- Build shared crates for:
  - config loading
  - structured logging
  - summary schema validation
- Keep Python as orchestrator.

**Exit criteria:** Rust crates built/tested in CI; no user-facing behavior change.

### M2 — Data & Contract Layer in Rust ✅ Implemented

- Move summary-contract validation and normalization into Rust library/service.
- Add compatibility fixtures to verify exact JSON output shape.
- Ensure SQLite read/write compatibility with existing schema.

**Exit criteria:** contract parity with Python implementation on fixture corpus.

### M3 — Processing Pipeline Migration ✅ Implemented

- Migrate URL/content processing pipeline in slices:
  1. content extraction adapter
  2. chunking + preprocessing
  3. LLM orchestration wrappers
- Run shadow mode (Python authoritative, Rust comparison path).

**Exit criteria:** shadow mismatch rate below agreed threshold; no regression in p95 latency.

### M4 — Interface Layer Migration

- Migrate mobile API and Telegram command routing to Rust.
- Keep identical API paths and response contracts.
- Preserve auth/rate-limiting behavior and operational tooling.

**Exit criteria:** canary traffic served by Rust path with rollback switch.

### M5 — Cutover and Decommission

- Default production traffic to Rust runtime.
- Keep Python fallback for one release window.
- Remove deprecated Python paths once stability SLO is met.

**Exit criteria:** fallback unused for release window; decommission plan complete.


## Milestone Implementation Notes

- **M0 artifacts**
  - Parity suite entrypoint: `scripts/migration/run_parity_suite.sh`
  - Baseline metrics capture: `scripts/migration/capture_python_baseline.py`
  - Baseline output: `docs/migration/baseline_metrics.json`
  - History log: `docs/migration/baseline_metrics_history.jsonl`
- **M1 artifacts**
  - Rust workspace: `rust/Cargo.toml`
  - Shared crates: `rust/crates/bsr-config`, `rust/crates/bsr-logging`, `rust/crates/bsr-summary-contract`
  - CI jobs: `parity-suite` and `rust-foundation` in `.github/workflows/ci.yml`
- **M2 artifacts**
  - Rust summary contract service: `rust/crates/bsr-summary-contract/src/lib.rs`, `src/main.rs`
  - Python backend toggle bridge: `app/core/summary_contract_impl/rust_backend.py`
  - Fixture corpus: `docs/migration/fixtures/m2_summary_contract/`
  - Fixture generator/check: `scripts/migration/generate_m2_contract_fixtures.py`
  - M2 suite runner: `scripts/migration/run_m2_parity_suite.sh` (`make m2-parity-suite`)
  - CI job: `m2-contract-parity` in `.github/workflows/ci.yml`
  - Detailed notes: `docs/migration/m2.md`
- **M3 artifacts**
  - Rust pipeline shadow service: `rust/crates/bsr-pipeline-shadow/src/lib.rs`, `src/main.rs`
  - Python shadow runner: `app/migration/pipeline_shadow.py`
  - Shadow hooks in runtime flow: `app/adapters/content/url_processor.py`, `app/adapters/content/llm_summarizer.py`
  - Fixture corpus: `docs/migration/fixtures/m3_pipeline_shadow/`
  - Fixture generator/check: `scripts/migration/generate_m3_shadow_fixtures.py`
  - M3 suite runner: `scripts/migration/run_m3_parity_suite.sh` (`make m3-parity-suite`)
  - CI job: `m3-pipeline-shadow-parity` in `.github/workflows/ci.yml`
  - Detailed notes: `docs/migration/m3.md`

## Cross-Cutting Workstreams

- **Testing:** parity, characterization, integration, load, and migration tests.
- **Observability:** unified metrics/log/tracing across Python and Rust components.
- **Security:** dependency scanning, secrets handling, auth parity checks.
- **Operations:** deployment templates, rollback docs, runbooks.

## Risks and Mitigations

- **Behavior drift:** enforce contract tests and golden fixtures.
- **Schema drift:** migration tests against production-like snapshots.
- **Operational complexity during dual runtime:** strict ownership per slice and feature flags.
- **Team velocity drop:** keep slices small and reversible.

## Documentation Requirements per Milestone

Each milestone PR must update:

1. `README.md` (runtime status)
2. `docs/README.md` (navigation and migration status)
3. Relevant reference/how-to docs in `docs/`
4. This roadmap file (`ROADMAP.md`)

## Success Metrics

- p95 summarize latency improvement vs Python baseline
- Memory usage reduction under representative load
- Error-rate parity or better
- 100% pass rate for parity contract suite

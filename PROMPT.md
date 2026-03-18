# Bite-Size Reader: Full Python -> Rust Migration

## Objective

Complete the remaining migration to a Rust runtime so production behavior no longer depends on Python execution paths, while preserving all external contracts.

## Source of Truth

- `ROADMAP.md`
- `docs/SPEC.md`
- `docs/migration/m0-m1.md`
- `docs/migration/m2.md`
- `docs/migration/m3.md`
- `docs/migration/m4.md`
- `docs/migration/m5.md`
- `docs/reference/api-contracts.md`
- `docs/reference/summary-contract.md`
- `docs/reference/data-model.md`

## Current State (must preserve)

- M2/M3/M4/M5 migrated slices already exist in Rust (`rust/crates/*`).
- API/bot behavior, command semantics, and JSON summary contract are frozen.
- SQLite schema/data compatibility is mandatory.

## Non-Negotiable Constraints

1. No behavior drift for Telegram commands, Mobile API contracts, or summary JSON contract.
2. Keep SQLite compatibility with existing production snapshots/data files.
3. Deliver in small reversible slices with explicit rollback notes per slice.
4. Keep all migration parity suites green at each milestone.
5. Do not remove observability, logging, or cutover event instrumentation.

## Scope of Work

1. Inventory remaining Python-owned runtime surfaces under `app/` and map each to Rust target crates/binaries.
2. Implement Rust replacements for remaining runtime-critical paths (bot orchestration, API execution path, persistence/service orchestration still owned by Python).
3. Integrate Rust components with stable interfaces and remove/decommission Python runtime execution paths once parity is proven.
4. Update CI, scripts, and docs to reflect Rust-authoritative execution and fallback decommission.

## Execution Plan

1. Produce a migration inventory matrix (`python module -> rust crate/bin -> parity test -> rollback switch`).
2. Migrate one vertical slice at a time (interface + domain + persistence + telemetry) with tests.
3. After each slice:
   - run targeted Rust + Python parity tests
   - fix regressions immediately
   - update docs/roadmap status
4. Finalize by removing deprecated Python runtime paths and ensuring operator docs only describe Rust-first execution.

## Required Verification Commands

- `cargo check --workspace --manifest-path rust/Cargo.toml`
- `cargo test --workspace --manifest-path rust/Cargo.toml`
- `bash scripts/migration/run_m2_parity_suite.sh`
- `bash scripts/migration/run_m3_parity_suite.sh`
- `bash scripts/migration/run_m4_parity_suite.sh`
- `bash scripts/migration/run_m5_cutover_suite.sh`
- `bash scripts/migration/run_parity_suite.sh`

## Acceptance Criteria (Given/When/Then)

1. Given frozen contracts, when Telegram/mobile API/summary flows execute, then responses match documented contracts with no breaking drift.
2. Given existing SQLite snapshots, when Rust compatibility + roundtrip tests run, then schema compatibility and write/read smoke pass.
3. Given migration suites, when M2+M3+M4+M5 suites run, then all pass without manual patching.
4. Given decommissioned paths, when legacy Python runtime toggles are set, then they are either ignored with clear warnings or rejected by validation (no silent fallback).
5. Given CI pipeline, when repository checks run, then Rust workspace and migration suites are enforced.
6. Given docs, when operators read migration/runtime guides, then they reflect Rust-first authoritative runtime and current rollback policy.

## Deliverables

- Rust code for remaining runtime surfaces.
- Removed/decommissioned Python runtime execution paths.
- Updated tests/fixtures/parity coverage.
- Updated `README.md`, `docs/README.md`, `docs/how-to/migrate-versions.md`, `ROADMAP.md`, and relevant migration docs.
- Final migration report summarizing changed files, parity evidence, and residual risks.

## Completion Protocol

When done, print exactly: `LOOP_COMPLETE`

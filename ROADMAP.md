# Roadmap: Python → Rust Migration

This roadmap tracks the project-wide migration from the current Python runtime to a Rust-first runtime while preserving API and bot behavior.

## Migration Goals

- Preserve existing user workflows (`/summarize`, `/search`, `/digest`, mobile API, MCP).
- Keep SQLite data compatible during and after migration.
- Ship in incremental slices with rollback points.
- Reduce memory footprint and improve throughput/latency in production.

## Current State

- **Production runtime:** Rust-first
- **Target runtime:** Rust
- **Migration mode:** Cutover and fallback decommission completed for migrated slices

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
  3. chunk sentence planning
  4. content cleaning
  5. LLM orchestration wrappers
  6. chunk summary aggregation
  7. chunk synthesis prompt assembly
  8. summary user-content payload assembly
- Enforce Rust-authoritative execution for M3 slices (fallback-disabled modes decommissioned).

**Exit criteria:** Rust-authoritative M3 slice execution enforced with parity fixtures and no regression in p95 latency.

### M4 — Interface Layer Migration ✅ Implemented

- Migrate mobile API and Telegram command routing to Rust.
- Keep identical API paths and response contracts.
- Preserve auth/rate-limiting behavior and operational tooling.

**Exit criteria:** canary traffic served by Rust path with rollback switch.

### M5 — Cutover and Decommission ✅ Implemented

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
  - Python runtime bridge (authoritative + parity helpers): `app/migration/pipeline_shadow.py`
  - Runtime hooks in flow: `app/adapters/content/url_processor.py`, `app/adapters/content/llm_summarizer.py`
  - Fixture corpus: `docs/migration/fixtures/m3_pipeline_shadow/`
  - Fixture generator/check: `scripts/migration/generate_m3_shadow_fixtures.py`
  - M3 suite runner: `scripts/migration/run_m3_parity_suite.sh` (`make m3-parity-suite`)
  - CI job: `m3-pipeline-shadow-parity` in `.github/workflows/ci.yml`
  - Detailed notes: `docs/migration/m3.md`
- **M4 artifacts**
  - Rust interface router service: `rust/crates/bsr-interface-router/src/lib.rs`, `src/main.rs`
  - Python interface router integration bridge: `app/migration/interface_router.py`
  - Runtime hooks for interface routing:
    - Mobile API middleware: `app/api/middleware.py`
  - Fixture corpus: `docs/migration/fixtures/m4_interface_routing/`
  - Fixture generator/check: `scripts/migration/generate_m4_interface_fixtures.py`
  - M4 suite runner: `scripts/migration/run_m4_parity_suite.sh` (`make m4-parity-suite`)
  - CI job: `m4-interface-router-parity` in `.github/workflows/ci.yml`
  - Detailed notes: `docs/migration/m4.md`
- **M5 artifacts**
  - Rust-first cutover defaults:
    - `app/core/summary_contract_impl/rust_backend.py` (`SUMMARY_CONTRACT_BACKEND` default)
    - `app/config/runtime.py` (`MIGRATION_INTERFACE_BACKEND` default)
  - Python fallback decommission for migrated slices:
    - Summary contract: `app/core/summary_contract_impl/rust_backend.py`
    - Interface routing: `app/migration/interface_router.py`, `app/api/middleware.py`
  - Cutover fallback event monitor:
    - `app/migration/cutover_monitor.py`
  - Release-window fallback checker:
    - `scripts/migration/check_m5_cutover_window.py`
  - M5 suite runner: `scripts/migration/run_m5_cutover_suite.sh` (`make m5-cutover-suite`)
  - CI job: `m5-cutover-suite` in `.github/workflows/ci.yml`
  - Detailed notes: `docs/migration/m5.md`
- **Post-M5 planning artifact**
  - Runtime ownership matrix for remaining Python-owned surfaces:
    - `docs/migration/runtime-inventory-matrix.md`
- **Post-M5 first implementation slice (M6-S1 scaffold implemented)**
  - Telegram command lifecycle decision scaffold (Rust route decisions,
    Python handlers retained):
    - Rust scaffold crate: `rust/crates/bsr-telegram-runtime`
    - Python bridge: `app/migration/telegram_runtime.py`
    - Telegram route-decision wiring:
      `app/adapters/telegram/message_router.py`,
      `app/adapters/telegram/message_router_content.py`
    - Runtime toggle/config docs:
      `.env.example`, `docs/environment_variables.md`,
      `docs/how-to/migrate-versions.md`
    - M6 suite runner and CI enforcement:
      `scripts/migration/run_m6_telegram_runtime_suite.sh`,
      `make m6-telegram-runtime-suite`, `m6-telegram-runtime-suite` job in
      `.github/workflows/ci.yml`
    - Planning/status record:
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S3 fail-closed hardening:
      `app/migration/telegram_runtime.py`,
      `tests/test_telegram_runtime_runner.py`
    - M6-S4 config hardening (invalid backend rejection, no implicit fallback):
      `app/migration/telegram_runtime.py`,
      `tests/test_telegram_runtime_runner.py`
    - M6-S5 rollout posture hardening (rust-default backend prior to fallback decommission):
      `app/config/runtime.py`, `app/migration/telegram_runtime.py`,
      `.env.example`, `docs/environment_variables.md`,
      `docs/how-to/migrate-versions.md`
    - M6-S6 fallback decommission (rust-only backend, python mode rejected):
      `app/config/runtime.py`, `app/migration/telegram_runtime.py`,
      `tests/test_runtime_config_migration_flags.py`,
      `tests/test_telegram_runtime_runner.py`,
      `.env.example`, `docs/environment_variables.md`,
      `docs/how-to/migrate-versions.md`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S7 message-router hardening (legacy interface-router command fallback removed):
      `app/adapters/telegram/message_router_content.py`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S8 wiring cleanup hardening (remove stale Telegram interface-router runner construction):
      `app/adapters/telegram/message_router.py`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S9 backend-toggle decommission cleanup (remove redundant Telegram backend config field):
      `app/config/runtime.py`, `app/migration/telegram_runtime.py`,
      `tests/test_runtime_config_migration_flags.py`,
      `tests/test_telegram_runtime_runner.py`,
      `.env.example`, `docs/environment_variables.md`,
      `docs/how-to/migrate-versions.md`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S10 decommission observability hardening (warn on legacy Telegram backend env toggle):
      `app/config/settings.py`, `tests/test_model_validation.py`,
      `docs/environment_variables.md`,
      `docs/how-to/migrate-versions.md`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S11 documentation drift hardening (remove stale backend-toggle rollout guidance):
      `rust/README.md`
    - M6-S12 command-dispatch complexity hardening (table-driven Telegram command routing):
      `app/adapters/telegram/message_router_content.py`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S13 bot-mention alias parity hardening (explicit `@bot` alias coverage in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S14 bot-mention stateful-command parity hardening (explicit `@bot` coverage for `/summarize` and `/cancel` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S15 bot-mention argument-command parity hardening (explicit `@bot` + trailing-argument coverage for `/search` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S16 bot-mention core-command parity hardening (explicit `@bot` coverage for `/start` and `/help` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S17 bot-mention find-alias parity hardening (explicit `@bot` coverage for `/findweb` and `/find` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S18 bot-mention summarize-all parity hardening (explicit `@bot` coverage for `/summarize_all` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S19 bot-mention unread/read parity hardening (explicit `@bot` coverage for `/unread` and `/read` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S20 bot-mention db-admin parity hardening (explicit `@bot` coverage for `/dbinfo`, `/dbverify`, and `/clearcache` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S21 bot-mention canonical local-search parity hardening (explicit `@bot` coverage for `/finddb` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S22 bot-mention session/diagnostic parity hardening (explicit `@bot` coverage for `/init_session`, `/settings`, and `/debug` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S23 bot-mention utility/admin parity hardening (explicit `@bot` coverage for `/sync_karakeep`, `/cdigest`, `/digest`, `/channels`, `/subscribe`, and `/unsubscribe` in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S24 unknown-command bot-mention parity hardening (explicit `@bot` coverage for unknown command passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S25 mixed-case bot-mention parity hardening (explicit `@bot` coverage for mixed-case command non-handled semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S26 mixed-case bot-username mention parity hardening (explicit mixed-case username `@bot` coverage for known-command canonical dispatch in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S27 empty bot-mention suffix parity hardening (explicit empty-username `@bot` suffix coverage for known-command canonical dispatch in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S28 mixed-case command + mixed-case bot-mention parity hardening (explicit mixed-case command with mixed-case username `@bot` coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S29 unknown-command mixed-case bot-mention parity hardening (explicit unknown-command fixture with mixed-case username `@bot` coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S30 unknown-command empty bot-mention suffix parity hardening (explicit unknown-command fixture with empty username `@bot` suffix coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S31 mixed-case command empty bot-mention suffix parity hardening (explicit mixed-case command fixture with empty username `@bot` suffix coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S32 unknown mixed-case command bot-mention parity hardening (explicit mixed-case unknown-command fixture with lowercase username `@bot` coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S33 unknown mixed-case command mixed-case bot-mention parity hardening (explicit mixed-case unknown-command fixture with mixed-case username `@bot` coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S34 unknown mixed-case command empty-mention parity hardening (explicit mixed-case unknown-command fixture with empty username `@bot` suffix coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S35 unknown mixed-case command no-mention parity hardening (explicit mixed-case unknown-command fixture without `@bot` mention coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S36 unknown command no-mention parity hardening (explicit lowercase unknown-command fixture without `@bot` mention coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S37 unknown command bare no-mention parity hardening (explicit lowercase unknown-command fixture without `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S38 unknown mixed-case command bare no-mention parity hardening (explicit mixed-case unknown-command fixture without `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S39 unknown command bare bot-mention parity hardening (explicit lowercase unknown-command fixture with lowercase username `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S40 unknown mixed-case command bare bot-mention parity hardening (explicit mixed-case unknown-command fixture with lowercase username `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S41 unknown command bare mixed-case bot-mention parity hardening (explicit lowercase unknown-command fixture with mixed-case username `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S42 unknown mixed-case command bare mixed-case bot-mention parity hardening (explicit mixed-case unknown-command fixture with mixed-case username `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S43 unknown command bare empty bot-mention suffix parity hardening (explicit lowercase unknown-command fixture with empty username suffix `@` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S44 unknown mixed-case command bare empty bot-mention suffix parity hardening (explicit mixed-case unknown-command fixture with empty username suffix `@` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S45 mixed-case command bare bot-mention case-sensitivity parity hardening (explicit mixed-case known-alias fixture with lowercase username `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S46 mixed-case command bare mixed-case bot-mention case-sensitivity parity hardening (explicit mixed-case known-alias fixture with mixed-case username `@bot` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S47 mixed-case command bare empty bot-mention suffix case-sensitivity parity hardening (explicit mixed-case known-alias fixture with empty username suffix `@` mention and without trailing arguments coverage for non-handled passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S48 lowercase known command bare bot-mention normalization parity hardening (explicit lowercase known-alias fixture `/findonline@mybot` without trailing arguments coverage to preserve handled canonical normalization and alias payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S49 lowercase known command bare mixed-case bot-mention normalization parity hardening (explicit lowercase known-alias fixture `/findonline@MyBot` without trailing arguments coverage to preserve handled canonical normalization and alias payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S50 lowercase known command bare empty bot-mention suffix normalization parity hardening (explicit lowercase known-alias fixture `/findonline@` without trailing arguments coverage to preserve handled canonical normalization and alias payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S51 lowercase canonical command bare bot-mention normalization parity hardening (explicit lowercase canonical fixture `/find@mybot` without trailing arguments coverage to preserve handled canonical normalization and command payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S52 lowercase canonical command bare mixed-case bot-mention normalization parity hardening (explicit lowercase canonical fixture `/find@MyBot` without trailing arguments coverage to preserve handled canonical normalization and command payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S53 lowercase canonical command bare empty bot-mention suffix normalization parity hardening (explicit lowercase canonical fixture `/find@` without trailing arguments coverage to preserve handled canonical normalization and command payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S54 lowercase canonical command empty bot-mention suffix argument normalization parity hardening (explicit lowercase canonical fixture `/find@ rust` with trailing arguments coverage to preserve handled canonical normalization and command payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S55 lowercase canonical command mixed-case bot-mention argument normalization parity hardening (explicit lowercase canonical fixture `/find@MyBot rust` with trailing arguments coverage to preserve handled canonical normalization and command payload semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S56 mixed-case canonical command bot-mention argument case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find@mybot rust` with trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S57 mixed-case canonical command mixed-case bot-mention argument case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find@MyBot rust` with trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S58 mixed-case canonical command bare bot-mention case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find@mybot` without trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S59 mixed-case canonical command bare mixed-case bot-mention case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find@MyBot` without trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S60 mixed-case canonical command empty bot-mention suffix argument case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find@ rust` with trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S61 mixed-case canonical command bare empty bot-mention suffix case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find@` without trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S62 mixed-case canonical command no-mention argument case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find rust` with trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S63 mixed-case canonical bare no-mention case-sensitivity parity hardening (explicit mixed-case canonical fixture `/Find` without trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S64 mixed-case known command bare no-mention case-sensitivity parity hardening (explicit mixed-case known fixture `/Findonline` without trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S65 mixed-case known command no-mention argument case-sensitivity parity hardening (explicit mixed-case known fixture `/Findonline rust` with trailing arguments coverage to preserve non-handled case-sensitive passthrough semantics in Rust + bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S66 leading-whitespace command-shape parity hardening (command-like fixture with leading whitespace `" /findonline rust"` is explicitly covered to preserve non-handled passthrough semantics and slash-at-start command gating across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S67 no-leading-slash command-shape parity hardening (command-like fixture without a leading slash `"findonline rust"` is explicitly covered to preserve non-handled passthrough semantics and slash-at-start command gating across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S68 slash-only command-shape parity hardening (slash-only fixture
      `"/"` is explicitly covered to preserve non-handled passthrough semantics
      for command-shaped text without a canonical command token across Rust
      route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S69 slash-space command-shape parity hardening (slash-space fixture
      `"/ findonline rust"` is explicitly covered to preserve non-handled
      passthrough semantics for command-shaped text where slash is not followed
      by a command token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S70 slash-tab command-shape parity hardening (slash-tab fixture
      `"/\tfindonline rust"` is explicitly covered to preserve non-handled
      passthrough semantics for command-shaped text where slash is followed by
      whitespace instead of a command token across Rust route decisions +
      Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S71 slash-newline command-shape parity hardening (slash-newline
      fixture `"/\nfindonline rust"` is explicitly covered to preserve
      non-handled passthrough semantics for command-shaped text where slash is
      followed by a newline instead of a command token across Rust route
      decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S72 slash-carriage-return command-shape parity hardening
      (slash-carriage-return fixture `"/\rfindonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a carriage return instead of a command
      token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S73 slash-form-feed command-shape parity hardening (slash-form-feed
      fixture `"/\ffindonline rust"` is explicitly covered to preserve
      non-handled passthrough semantics for command-shaped text where slash is
      followed by a form feed instead of a command token across Rust route
      decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S74 slash-vertical-tab command-shape parity hardening
      (slash-vertical-tab fixture `"/\vfindonline rust"` is explicitly covered
      to preserve non-handled passthrough semantics for command-shaped text
      where slash is followed by a vertical tab instead of a command token
      across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S75 slash-non-breaking-space command-shape parity hardening
      (slash-non-breaking-space fixture `"/\u00A0findonline rust"` is
      explicitly covered to preserve non-handled passthrough semantics for
      command-shaped text where slash is followed by a non-breaking space
      instead of a command token across Rust route decisions + Python bridge
      tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S76 slash-narrow-no-break-space command-shape parity hardening
      (slash-narrow-no-break-space fixture `"/\u202Ffindonline rust"` is
      explicitly covered to preserve non-handled passthrough semantics for
      command-shaped text where slash is followed by a narrow no-break space
      instead of a command token across Rust route decisions + Python bridge
      tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S77 slash-figure-space command-shape parity hardening
      (slash-figure-space fixture `"/\u2007findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a figure space instead of a command token
      across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S78 slash-ideographic-space command-shape parity hardening
      (slash-ideographic-space fixture `"/\u3000findonline rust"` is
      explicitly covered to preserve non-handled passthrough semantics for
      command-shaped text where slash is followed by an ideographic space
      instead of a command token across Rust route decisions + Python bridge
      tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S79 slash-thin-space command-shape parity hardening
      (slash-thin-space fixture `"/\u2009findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a thin space instead of a command token
      across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S80 slash-hair-space command-shape parity hardening
      (slash-hair-space fixture `"/\u200Afindonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a hair space instead of a command token
      across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S81 slash-medium-mathematical-space command-shape parity hardening
      (slash-medium-mathematical-space fixture `"/\u205Ffindonline rust"` is
      explicitly covered to preserve non-handled passthrough semantics for
      command-shaped text where slash is followed by a medium mathematical
      space instead of a command token across Rust route decisions + Python
      bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S82 slash-punctuation-space command-shape parity hardening
      (slash-punctuation-space fixture `"/\u2008findonline rust"` is
      explicitly covered to preserve non-handled passthrough semantics for
      command-shaped text where slash is followed by a punctuation space
      instead of a command token across Rust route decisions + Python bridge
      tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S83 slash-six-per-em-space command-shape parity hardening
      (slash-six-per-em-space fixture `"/\u2006findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a six-per-em space instead of a command
      token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S84 slash-four-per-em-space command-shape parity hardening
      (slash-four-per-em-space fixture `"/\u2005findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a four-per-em space instead of a command
      token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S85 slash-three-per-em-space command-shape parity hardening
      (slash-three-per-em-space fixture `"/\u2004findonline rust"` is
      explicitly covered to preserve non-handled passthrough semantics for
      command-shaped text where slash is followed by a three-per-em space
      instead of a command token across Rust route decisions + Python bridge
      tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S86 slash-em-space command-shape parity hardening
      (slash-em-space fixture `"/\u2003findonline rust"` is explicitly covered
      to preserve non-handled passthrough semantics for command-shaped text
      where slash is followed by an em space instead of a command token across
      Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S87 slash-en-space command-shape parity hardening
      (slash-en-space fixture `"/\u2002findonline rust"` is explicitly covered
      to preserve non-handled passthrough semantics for command-shaped text
      where slash is followed by an en space instead of a command token across
      Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S88 slash-em-quad-space command-shape parity hardening
      (slash-em-quad-space fixture `"/\u2001findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by an em quad space instead of a command
      token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S89 slash-en-quad-space command-shape parity hardening
      (slash-en-quad-space fixture `"/\u2000findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by an en quad space instead of a command
      token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S90 slash-Ogham-space-mark command-shape parity hardening
      (slash-Ogham-space-mark fixture `"/\u1680findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by an Ogham space mark instead of a command
      token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S91 slash-line-separator command-shape parity hardening
      (slash-line-separator fixture `"/\u2028findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a line separator instead of a command
      token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S92 slash-paragraph-separator command-shape parity hardening
      (slash-paragraph-separator fixture `"/\u2029findonline rust"` is
      explicitly covered to preserve non-handled passthrough semantics for
      command-shaped text where slash is followed by a paragraph separator
      instead of a command token across Rust route decisions + Python bridge
      tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S93 slash-next-line command-shape parity hardening
      (slash-next-line fixture `"/\u0085findonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a next line character instead of a
      command token across Rust route decisions + Python bridge tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`
    - M6-S94 slash-file-separator command-shape parity hardening
      (slash-file-separator fixture `"/\u001Cfindonline rust"` is explicitly
      covered to preserve non-handled passthrough semantics for command-shaped
      text where slash is followed by a file separator control character
      instead of a command token across Rust route decisions + Python bridge
      tests):
      `rust/crates/bsr-telegram-runtime/src/lib.rs`,
      `tests/test_message_router_interface_routing.py`,
      `docs/migration/runtime-inventory-matrix.md`

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

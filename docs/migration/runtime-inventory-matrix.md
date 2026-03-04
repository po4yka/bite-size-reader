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
| M4 interface command/route selection | `app/migration/interface_router.py`, `app/api/middleware.py` | `rust/crates/bsr-interface-router` (`bsr-interface-router`) | `rust-authoritative` | `bash scripts/migration/run_m4_parity_suite.sh` | `MIGRATION_INTERFACE_BACKEND` (Rust required; non-rust values ignored) |
| Telegram bot orchestration and command lifecycle | `bot.py`, `app/adapters/telegram/*`, `app/handlers/*` | `rust/crates/bsr-telegram-runtime` + `rust/bin/bsr-bot` | `python-owned` | `bash scripts/migration/run_m6_telegram_runtime_suite.sh` (Rust command parity + Python bridge checks) | `MIGRATION_TELEGRAM_RUNTIME_TIMEOUT_MS` (backend fixed to Rust; legacy backend toggle ignored) |
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

## First Post-Inventory Runtime Slice (M6-S1, Scaffold Implemented)

First implementation slice after inventory lock:

- **Surface:** Telegram bot orchestration and command lifecycle.
- **Slice objective:** Move Telegram ingress classification and command route
  decisions to Rust while keeping downstream command handlers/persistence in
  their current Python runtime paths.
- **Rust target:** `rust/crates/bsr-telegram-runtime` + `rust/bin/bsr-bot`
  (decision-only path for this slice).
- **Python integration point:** `bot.py` + `app/adapters/telegram/message_router.py`
  bridge to Rust decision output.
- **Delivered scaffold artifacts:**
  - `rust/crates/bsr-telegram-runtime` (`command-route` CLI + canonical
    command mapping tests).
  - `app/migration/telegram_runtime.py` runner bridge with Rust failure event
    capture and fail-closed errors in `rust` backend mode.
  - Telegram command route-decision wiring in
    `app/adapters/telegram/message_router.py` and
    `app/adapters/telegram/message_router_content.py`.
- **Parity harness status:** command route parity coverage now includes Rust
  crate tests against expanded M4 telegram-command fixtures (aliases,
  non-command URL/plain text, unknown commands, and forwarded-ingress
  command/non-command payloads).
- **Rollback switch policy:** command-route backend is fixed to Rust.
  Legacy `MIGRATION_TELEGRAM_RUNTIME_BACKEND` values are ignored with warning
  telemetry (no implicit or explicit Python fallback path).
- **Routing ownership hardening:** `MessageRouterContentMixin` now requires
  `telegram_runtime_runner`; legacy command fallback through
  `interface_router` is decommissioned.
- **Wiring cleanup hardening (M6-S8):** `MessageRouter` no longer constructs an
  `InterfaceRouterRunner` instance for Telegram flows; command routing runtime
  ownership is exclusively `telegram_runtime_runner`.
- **Command dispatch hardening (M6-S12):** command routing in
  `MessageRouterContentMixin` is table-driven via shared dispatch helpers,
  preserving alias semantics while reducing branch complexity in the
  Python-side bridge.
- **Bot-mention alias parity hardening (M6-S13):** explicit alias-command
  fixtures with `@bot` mentions are covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  mention-stripping parity stable for `/findonline` and `/findlocal`.
- **Bot-mention stateful-command parity hardening (M6-S14):** explicit
  `@bot` mention fixtures for `/summarize` and `/cancel` are covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  stateful command-route behavior stable.
- **Bot-mention argument-command parity hardening (M6-S15):** explicit
  `@bot` mention fixture with trailing arguments for `/search` is covered in
  both `bsr-telegram-runtime` Rust tests and Python bridge routing tests to
  keep text-command payload semantics stable for argument-bearing commands.
- **Bot-mention core-command parity hardening (M6-S16):** explicit `@bot`
  mention fixtures for `/start` and `/help` are covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  core command-route dispatch stable for bot-directed invocations.
- **Bot-mention find-alias parity hardening (M6-S17):** explicit `@bot`
  mention fixtures for `/findweb` and `/find` are covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  online-search alias dispatch stable for bot-directed invocations.
- **Bot-mention summarize-all parity hardening (M6-S18):** explicit `@bot`
  mention fixture for `/summarize_all` is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  summarize-all command-route dispatch stable for bot-directed invocations.
- **Bot-mention unread/read parity hardening (M6-S19):** explicit `@bot`
  mention fixtures for `/unread` and `/read` are covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unread/read command-route dispatch stable for bot-directed invocations.
- **Bot-mention db-admin parity hardening (M6-S20):** explicit `@bot`
  mention fixtures for `/dbinfo`, `/dbverify`, and `/clearcache` are covered
  in both `bsr-telegram-runtime` Rust tests and Python bridge routing tests to
  keep admin command-route dispatch stable for bot-directed invocations.
- **Bot-mention canonical local-search parity hardening (M6-S21):** explicit
  `@bot` mention fixture for canonical `/finddb` is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  local-search canonical dispatch stable for bot-directed invocations.
- **Bot-mention session/diagnostic parity hardening (M6-S22):** explicit
  `@bot` mention fixtures for `/init_session`, `/settings`, and `/debug` are
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep session/diagnostic command-route dispatch stable for
  bot-directed invocations.
- **Bot-mention utility/admin parity hardening (M6-S23):** explicit `@bot`
  mention fixtures for `/sync_karakeep`, `/cdigest`, `/digest`, `/channels`,
  `/subscribe`, and `/unsubscribe` are covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  utility/admin command-route dispatch stable for bot-directed invocations.
- **Unknown-command bot-mention parity hardening (M6-S24):** explicit `@bot`
  mention fixture for unknown command passthrough is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command non-handled semantics stable for bot-directed invocations.
- **Mixed-case bot-mention parity hardening (M6-S25):** explicit `@bot`
  mention fixture for mixed-case command passthrough is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  case-sensitive non-handled semantics stable for bot-directed invocations.
- **Mixed-case bot-username mention parity hardening (M6-S26):** explicit
  mixed-case username `@bot` fixture for known-command canonical dispatch is
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep bot-username casing behavior stable for bot-directed
  invocations.
- **Empty bot-mention suffix parity hardening (M6-S27):** explicit empty
  username `@bot` suffix fixture for known-command canonical dispatch is
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep empty-mention suffix behavior stable for bot-directed
  invocations.
- **Mixed-case command + mixed-case bot-mention parity hardening (M6-S28):**
  explicit mixed-case command with mixed-case username `@bot` fixture for
  non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  case-sensitive mention behavior stable for bot-directed invocations.
- **Unknown-command mixed-case bot-mention parity hardening (M6-S29):**
  explicit unknown-command fixture with mixed-case username `@bot` for
  non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command mention-casing behavior stable for bot-directed invocations.
- **Unknown-command empty bot-mention suffix parity hardening (M6-S30):**
  explicit unknown-command fixture with empty username `@bot` suffix for
  non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command empty-mention suffix behavior stable for bot-directed
  invocations.
- **Mixed-case command empty bot-mention suffix parity hardening (M6-S31):**
  explicit mixed-case command fixture with empty username `@bot` suffix for
  non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  mixed-case empty-mention suffix behavior stable for bot-directed
  invocations.
- **Unknown mixed-case command bot-mention parity hardening (M6-S32):**
  explicit mixed-case unknown-command fixture with lowercase username `@bot`
  for non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command case-sensitive mention behavior stable for bot-directed
  invocations.
- **Unknown mixed-case command mixed-case bot-mention parity hardening
  (M6-S33):** explicit mixed-case unknown-command fixture with mixed-case
  username `@bot` for non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command case-sensitive mixed-case mention behavior stable for
  bot-directed invocations.
- **Unknown mixed-case command empty-mention parity hardening (M6-S34):**
  explicit mixed-case unknown-command fixture with empty username `@bot`
  suffix for non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command case-sensitive empty-mention suffix behavior stable for
  bot-directed invocations.
- **Unknown mixed-case command no-mention parity hardening (M6-S35):**
  explicit mixed-case unknown-command fixture without `@bot` mention for
  non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command case-sensitive no-mention behavior stable for direct command
  invocations.
- **Unknown command no-mention parity hardening (M6-S36):**
  explicit lowercase unknown-command fixture without `@bot` mention for
  non-handled passthrough semantics is covered in both
  `bsr-telegram-runtime` Rust tests and Python bridge routing tests to keep
  unknown-command no-mention behavior stable for direct command invocations.
- **Unknown command bare no-mention parity hardening (M6-S37):**
  explicit lowercase unknown-command fixture without `@bot` mention and
  without trailing arguments for non-handled passthrough semantics is covered
  in both `bsr-telegram-runtime` Rust tests and Python bridge routing tests to
  keep unknown-command bare no-mention behavior stable for direct command
  invocations.
- **Unknown mixed-case command bare no-mention parity hardening (M6-S38):**
  explicit mixed-case unknown-command fixture without `@bot` mention and
  without trailing arguments for non-handled passthrough semantics is covered
  in both `bsr-telegram-runtime` Rust tests and Python bridge routing tests to
  keep unknown-command case-sensitive bare no-mention behavior stable for
  direct command invocations.
- **Unknown command bare bot-mention parity hardening (M6-S39):**
  explicit lowercase unknown-command fixture with lowercase username `@bot`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep unknown-command bare bot-mention behavior stable for
  bot-directed command invocations.
- **Unknown mixed-case command bare bot-mention parity hardening (M6-S40):**
  explicit mixed-case unknown-command fixture with lowercase username `@bot`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep unknown-command case-sensitive bare bot-mention
  behavior stable for bot-directed command invocations.
- **Unknown command bare mixed-case bot-mention parity hardening (M6-S41):**
  explicit lowercase unknown-command fixture with mixed-case username `@bot`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep unknown-command bare mixed-case mention behavior stable
  for bot-directed command invocations.
- **Unknown mixed-case command bare mixed-case bot-mention parity hardening (M6-S42):**
  explicit mixed-case unknown-command fixture with mixed-case username `@bot`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep unknown-command case-sensitive bare mixed-case mention
  behavior stable for bot-directed command invocations.
- **Unknown command bare empty bot-mention suffix parity hardening (M6-S43):**
  explicit lowercase unknown-command fixture with empty username suffix `@`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep unknown-command bare empty-mention behavior stable for
  bot-directed command invocations.
- **Unknown mixed-case command bare empty bot-mention suffix parity hardening (M6-S44):**
  explicit mixed-case unknown-command fixture with empty username suffix `@`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep unknown-command case-sensitive bare empty-mention
  behavior stable for bot-directed command invocations.
- **Mixed-case command bare bot-mention case-sensitivity parity hardening (M6-S45):**
  explicit mixed-case known-alias fixture with lowercase username `@bot`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep known-command case-sensitive bare bot-mention behavior
  stable for bot-directed command invocations.
- **Mixed-case command bare mixed-case bot-mention case-sensitivity parity hardening (M6-S46):**
  explicit mixed-case known-alias fixture with mixed-case username `@bot`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep known-command case-sensitive bare mixed-case mention
  behavior stable for bot-directed command invocations.
- **Mixed-case command bare empty bot-mention suffix case-sensitivity parity hardening (M6-S47):**
  explicit mixed-case known-alias fixture with empty username suffix `@`
  mention and without trailing arguments for non-handled passthrough semantics
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep known-command case-sensitive bare empty-mention
  behavior stable for bot-directed command invocations.
- **Lowercase known command bare bot-mention normalization parity hardening (M6-S48):**
  explicit lowercase known-alias fixture `/findonline@mybot` without trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep handled canonical normalization (`/find`) and
  original alias payload semantics stable for bare bot-directed command
  invocations.
- **Lowercase known command bare mixed-case bot-mention normalization parity hardening (M6-S49):**
  explicit lowercase known-alias fixture `/findonline@MyBot` without trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep handled canonical normalization (`/find`) and
  original alias payload semantics stable for bare bot-directed command
  invocations.
- **Lowercase known command bare empty bot-mention suffix normalization parity hardening (M6-S50):**
  explicit lowercase known-alias fixture `/findonline@` without trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep handled canonical normalization (`/find`) and
  original alias payload semantics stable for bare bot-directed command
  invocations.
- **Lowercase canonical command bare bot-mention normalization parity hardening (M6-S51):**
  explicit lowercase canonical fixture `/find@mybot` without trailing arguments
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep handled canonical normalization (`/find`) and command
  payload semantics stable for bare bot-directed command invocations.
- **Lowercase canonical command bare mixed-case bot-mention normalization parity hardening (M6-S52):**
  explicit lowercase canonical fixture `/find@MyBot` without trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep handled canonical normalization (`/find`) and
  command payload semantics stable for bare bot-directed command invocations.
- **Lowercase canonical command bare empty bot-mention suffix normalization parity hardening (M6-S53):**
  explicit lowercase canonical fixture `/find@` without trailing arguments is
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep handled canonical normalization (`/find`) and command payload
  semantics stable for bare bot-directed command invocations.
- **Lowercase canonical command empty bot-mention suffix argument normalization parity hardening (M6-S54):**
  explicit lowercase canonical fixture `/find@ rust` with trailing arguments
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep handled canonical normalization (`/find`) and command
  payload semantics stable for argumented bot-directed command invocations.
- **Lowercase canonical command mixed-case bot-mention argument normalization parity hardening (M6-S55):**
  explicit lowercase canonical fixture `/find@MyBot rust` with trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep handled canonical normalization (`/find`) and
  command payload semantics stable for argumented bot-directed command
  invocations.
- **Mixed-case canonical command bot-mention argument case-sensitivity parity hardening (M6-S56):**
  explicit mixed-case canonical fixture `/Find@mybot rust` with trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep non-handled case-sensitive passthrough
  semantics stable for argumented bot-directed command invocations.
- **Mixed-case canonical command mixed-case bot-mention argument case-sensitivity parity hardening (M6-S57):**
  explicit mixed-case canonical fixture `/Find@MyBot rust` with trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep non-handled case-sensitive passthrough
  semantics stable for argumented bot-directed command invocations.
- **Mixed-case canonical command bare bot-mention case-sensitivity parity hardening (M6-S58):**
  explicit mixed-case canonical fixture `/Find@mybot` without trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep non-handled case-sensitive passthrough
  semantics stable for bare bot-directed command invocations.
- **Mixed-case canonical command bare mixed-case bot-mention case-sensitivity parity hardening (M6-S59):**
  explicit mixed-case canonical fixture `/Find@MyBot` without trailing
  arguments is covered in both `bsr-telegram-runtime` Rust tests and Python
  bridge routing tests to keep non-handled case-sensitive passthrough
  semantics stable for bare bot-directed command invocations.
- **Mixed-case canonical command empty bot-mention suffix argument case-sensitivity parity hardening (M6-S60):**
  explicit mixed-case canonical fixture `/Find@ rust` with trailing arguments
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep non-handled case-sensitive passthrough semantics
  stable for argumented bot-directed command invocations.
- **Mixed-case canonical command bare empty bot-mention suffix case-sensitivity parity hardening (M6-S61):**
  explicit mixed-case canonical fixture `/Find@` without trailing arguments is
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep non-handled case-sensitive passthrough semantics stable for
  bare bot-directed command invocations.
- **Mixed-case canonical command no-mention argument case-sensitivity parity hardening (M6-S62):**
  explicit mixed-case canonical fixture `/Find rust` with trailing arguments is
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep non-handled case-sensitive passthrough semantics stable for
  argumented command invocations without bot mentions.
- **Mixed-case canonical bare no-mention case-sensitivity parity hardening (M6-S63):**
  explicit mixed-case canonical fixture `/Find` without trailing arguments is
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep non-handled case-sensitive passthrough semantics stable for
  bare command invocations without bot mentions.
- **Mixed-case known command bare no-mention case-sensitivity parity hardening (M6-S64):**
  explicit mixed-case known fixture `/Findonline` without trailing arguments is
  covered in both `bsr-telegram-runtime` Rust tests and Python bridge routing
  tests to keep non-handled case-sensitive passthrough semantics stable for
  bare command invocations without bot mentions.
- **Mixed-case known command no-mention argument case-sensitivity parity hardening (M6-S65):**
  explicit mixed-case known fixture `/Findonline rust` with trailing arguments
  is covered in both `bsr-telegram-runtime` Rust tests and Python bridge
  routing tests to keep non-handled case-sensitive passthrough semantics stable
  for argumented command invocations without bot mentions.
- **Leading-whitespace command-shape parity hardening (M6-S66):**
  command-like fixture with leading whitespace `" /findonline rust"` is now
  explicitly covered across existing `bsr-telegram-runtime` slash-at-start Rust
  command-route tests and Python bridge routing tests to keep non-handled
  passthrough semantics stable when slash-prefixed tokens are not at offset 0.
- **No-leading-slash command-shape parity hardening (M6-S67):**
  command-like fixture without a leading slash `"findonline rust"` is now
  explicitly covered across existing `bsr-telegram-runtime` slash-at-start Rust
  command-route tests and Python bridge routing tests to keep non-handled
  passthrough semantics stable when text does not begin with `/`.
- **Slash-only command-shape parity hardening (M6-S68):**
  slash-only fixture `"/"` is now explicitly covered in both
  `bsr-telegram-runtime` Rust command-route tests and Python bridge routing
  tests to keep non-handled passthrough semantics stable when command-shaped
  text lacks a canonical command token.
- **Slash-space command-shape parity hardening (M6-S69):**
  slash-space fixture `"/ findonline rust"` is now explicitly covered in both
  `bsr-telegram-runtime` Rust command-route tests and Python bridge routing
  tests to keep non-handled passthrough semantics stable when slash-prefixed
  text is not followed by a command token.
- **Slash-tab command-shape parity hardening (M6-S70):**
  slash-tab fixture `"/\tfindonline rust"` is now explicitly covered in both
  `bsr-telegram-runtime` Rust command-route tests and Python bridge routing
  tests to keep non-handled passthrough semantics stable when slash-prefixed
  text is followed by whitespace rather than a command token.
- **Slash-newline command-shape parity hardening (M6-S71):**
  slash-newline fixture `"/\nfindonline rust"` is now explicitly covered in
  both `bsr-telegram-runtime` Rust command-route tests and Python bridge
  routing tests to keep non-handled passthrough semantics stable when
  slash-prefixed text is followed by a newline rather than a command token.
- **Slash-carriage-return command-shape parity hardening (M6-S72):**
  slash-carriage-return fixture `"/\rfindonline rust"` is now explicitly
  covered in both `bsr-telegram-runtime` Rust command-route tests and Python
  bridge routing tests to keep non-handled passthrough semantics stable when
  slash-prefixed text is followed by a carriage return rather than a command
  token.
- **Slash-form-feed command-shape parity hardening (M6-S73):**
  slash-form-feed fixture `"/\ffindonline rust"` is now explicitly covered in
  both `bsr-telegram-runtime` Rust command-route tests and Python bridge
  routing tests to keep non-handled passthrough semantics stable when
  slash-prefixed text is followed by a form feed rather than a command token.
- **Slash-vertical-tab command-shape parity hardening (M6-S74):**
  slash-vertical-tab fixture `"/\vfindonline rust"` is now explicitly covered
  in both `bsr-telegram-runtime` Rust command-route tests and Python bridge
  routing tests to keep non-handled passthrough semantics stable when
  slash-prefixed text is followed by a vertical tab rather than a command
  token.
- **Slash-non-breaking-space command-shape parity hardening (M6-S75):**
  slash-non-breaking-space fixture `"/\u00A0findonline rust"` is now
  explicitly covered in both `bsr-telegram-runtime` Rust command-route tests
  and Python bridge routing tests to keep non-handled passthrough semantics
  stable when slash-prefixed text is followed by a non-breaking space rather
  than a command token.

Out-of-scope for M6-S1 (defer to later slices):

- LLM orchestration migration.
- SQLite persistence ownership migration.
- Mobile API runtime execution migration.
- MCP/gRPC server migration.

Implementation acceptance gates for M6-S1:

1. Telegram route decisions from Rust match frozen command semantics in
   `docs/SPEC.md` fixtures.
2. Existing observability/cutover events remain emitted on Rust decision
   failures.
3. Runtime execution remains Rust-only even if legacy backend toggles are set
   (`MIGRATION_TELEGRAM_RUNTIME_BACKEND` is ignored with a warning when present).

## Verification Baseline Before and After Each Slice

Run all required migration suites at each slice boundary:

- `cargo check --workspace --manifest-path rust/Cargo.toml`
- `cargo test --workspace --manifest-path rust/Cargo.toml`
- `bash scripts/migration/run_m2_parity_suite.sh`
- `bash scripts/migration/run_m3_parity_suite.sh`
- `bash scripts/migration/run_m4_parity_suite.sh`
- `bash scripts/migration/run_m5_cutover_suite.sh`
- `bash scripts/migration/run_m6_telegram_runtime_suite.sh`
- `uv run bash scripts/migration/run_parity_suite.sh`

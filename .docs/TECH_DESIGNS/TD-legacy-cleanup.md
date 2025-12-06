# Legacy Cleanup and Compatibility Reduction
- Date: 2025-12-06
- Author: AI (Cursor)

## Context
- Goal: remove legacy compatibility layers and unused modules across Telegram, Mobile API, search/storage adapters, and tests while preserving current behavior.
- Legacy criteria: unused modules with zero imports; compatibility shims for relocated modules; duplicate layers superseded by newer implementations; dead examples not wired into DI; error-path handling kept only for legacy formats.
- Docs alignment: `.docs/README.md` tracks migration from `docs/` to `.docs/`; this TD owns cleanup scope.

## Goals and Non-Goals
- Goals:
  - Remove Telegram enum shim (`app/core/telegram_enums.py`) and enforce direct model imports.
  - Remove Mobile API auth shim (`app/api/auth.py`); update routers to use `app/api/routers/auth`.
  - Drop unused repository wrapper (`app/repositories.py`) and unused presentation example directory.
  - Simplify Telegram batch result handling by removing legacy tuple format handling.
- Non-Goals:
  - Database schema changes or data migrations.
  - Feature additions to YouTube pipeline; only legacy paths would be removed if found.
  - Changes to external API contracts beyond import-path cleanup.

## Architecture / Flow
- Telegram routing: `message_router.process_batch_results` will treat unexpected formats uniformly as errors; legacy tuple `(url, success)` results are no longer accepted.
- Telegram models: import MessageEntityType directly from `app.models.telegram.telegram_enums`; shim is deleted.
- Mobile API: routers import dependencies from `app.api.routers.auth`; compatibility module is removed.
- Data access: unused `app/repositories.py` removed; code relies on `app.infrastructure.persistence.sqlite.repositories.*`.
- Presentation examples: remove `app/presentation` sample handlers to avoid confusion.

## Data Model / Contracts
- No schema changes. Removal of `app/repositories.py` eliminates unused async wrappers; primary repositories remain in `app.infrastructure.persistence.sqlite.repositories`.
- API authentication helpers remain in `app.api.routers.auth`; import surface updated.
- Telegram entity enums remain in `app.models.telegram.telegram_enums`.

## Decisions
- Delete compatibility shims `app/core/telegram_enums.py` and `app/api/auth.py`; update imports to canonical locations.
- Remove unused modules `app/repositories.py` and `app/presentation/example_handler.py` (and package).
- Treat legacy tuple results in Telegram batch processing as errors, not tolerated inputs.
- Keep YouTube pipeline unchanged; no explicit legacy paths found in current adapters.

## Risks and Mitigations
- Hidden dependencies on deleted shims: Mitigate by updating all imports and running focused tests.
- Older clients relying on tuple results: Fail fast with explicit errors; telemetry via logs.
- Documentation drift: `.docs/README.md` and ADR capture mapping and decisions; `SPEC.md` references updated as needed.

## Testing Strategy
- Run targeted pytest suites per `.docs/TESTING/test_plan_legacy_cleanup.md` (API auth, response contracts, Telegram routing, URL handling).
- Rely on existing integration tests for Telegram routing; add new tests if regressions appear.

## Rollout
- Apply code removals and import updates.
- Update docs referencing deprecated paths.
- Run targeted tests; if failures appear due to missing legacy behaviors, consider scoped adapters or feature flags rather than re-adding shims.

## Inventory Snapshot
| Area | Candidate | Action |
| --- | --- | --- |
| Telegram | `app/core/telegram_enums.py` | Remove shim, update imports |
| Telegram | Legacy tuple batch result handling | Remove support; treat as error |
| Mobile API | `app/api/auth.py` | Remove shim, update router imports |
| Data layer | `app/repositories.py` | Remove unused wrappers |
| Presentation | `app/presentation/*` | Remove unused example package |
| YouTube | None identified | Keep; re-evaluate when new legacy paths surface |

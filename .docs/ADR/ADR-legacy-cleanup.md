# Legacy Cleanup of Compatibility Shims and Unused Modules
- Status: Decided
- Date: 2025-12-06
- Author: AI (Cursor)

## Context
- Legacy compatibility layers (Telegram enums, Mobile API auth) and unused modules (repository wrappers, presentation examples) increased maintenance surface and risked divergence from current architecture.
- Batch routing in Telegram tolerated legacy tuple results, masking invalid return types.

## Decision
- Remove Telegram enum shim `app/core/telegram_enums.py` and update consumers to use `app.models.telegram.telegram_enums`.
- Remove Mobile API auth shim `app/api/auth.py`; routers import dependencies directly from `app.api.routers.auth`.
- Delete unused modules `app/repositories.py` and `app/presentation/*`.
- Treat legacy tuple results in Telegram batch processing as errors; do not convert them.

## Consequences
- Positive: Reduced surface area, clearer import paths, fewer compatibility layers to maintain, stricter validation of Telegram batch results.
- Negative: Older callers expecting shimmed imports or tuple results will fail fast; requires docs/tests alignment.

## Alternatives Considered
- Keep shims with deprecation warnings: rejected to avoid prolonged dual-path maintenance.
- Feature-flagging tuple handling: rejected as unnecessary complexity given absence of known callers.

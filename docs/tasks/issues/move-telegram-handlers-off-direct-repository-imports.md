---
title: Move Telegram handlers off direct repository / app.db imports
status: backlog
area: content
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Move Telegram handlers off direct repository / app.db imports #repo/ratatoskr #area/content #status/backlog 🔼

## Objective

Telegram presentation reaches past the application layer straight into `app/db/*` and `app/infrastructure/persistence/repositories/` across ~15 handler files. This breaks the architecture rule documented at `docs/explanation/architecture-overview.md` §"Runtime policy" — "presentation handlers call application use cases for business workflows" — and means any user-interaction-policy change has to be re-applied across the bot surface instead of in one service.

## Context

Confirmed by the hexagonal-layer audit on 2026-05-17.

Direct `app.db.user_interactions` imports (11 sites):

- `app/adapters/telegram/access_controller.py:9, 183`
- `app/adapters/telegram/routing/interactions.py:8, 76`
- All `app/adapters/telegram/command_handlers/*_handler.py` that log user activity.

Direct repository imports from handlers:

- `app/adapters/telegram/command_handlers/listen_handler.py:14-17` (`RequestRepository`, `SummaryRepository`)
- `app/adapters/telegram/command_handlers/rules_handler.py:15`
- `app/adapters/telegram/command_handlers/rss_handler.py:15`
- `app/adapters/telegram/command_handlers/export_command.py:19`
- `app/adapters/telegram/command_handlers/backup_handler.py:16`
- `app/adapters/telegram/callback_action_store.py:11-14`
- `app/adapters/telegram/summary_followup.py:14`

## Scope

- Introduce a `UserInteractionService` (or port + adapter) under `app/application/services/` that wraps `async_safe_update_user_interaction`.
- Migrate every Telegram handler in the list above to depend on the service / use case (via the existing `CommandRegistry` injection) instead of importing `app.db.user_interactions` or `app.infrastructure.persistence.repositories.*` directly.
- Keep the change behaviour-preserving — no new business logic.

## Acceptance criteria

- [ ] `rg "from app\.db\.user_interactions" app/adapters/telegram/` returns zero matches.
- [ ] `rg "from app\.infrastructure\.persistence\.repositories" app/adapters/telegram/` returns zero matches.
- [ ] All existing Telegram handler tests pass unchanged.
- [ ] mypy + ruff clean.

## References

- Architecture rule: `docs/explanation/architecture-overview.md` §"Runtime policy" and §"Layer Map (project-specific)"
- Existing application-layer port pattern: `app/application/ports/`
- Existing service example: `app/application/services/digest_facade.py`

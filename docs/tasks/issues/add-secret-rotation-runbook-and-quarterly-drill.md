---
title: Add secret-rotation runbook and quarterly drill template
status: backlog
area: ops
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add secret-rotation runbook and quarterly drill template #repo/ratatoskr #area/ops #status/backlog 🔼

## Objective

`app/security/token_crypto.py:6-11` documents GitHub-token Fernet rotation steps inline in the module docstring, and `app/cli/rotate_github_tokens` exists — but `docs/runbooks/` has no `secret-rotation.md`. JWT signing key rotation: zero references. `BOT_TOKEN` rotation: zero references. No scheduled reminder, calendar entry, or drill template. Secrets that are never rotated become "secret in name only"; bot-token leaks need a known rotation flow.

## Context

- Existing inline doc: `app/security/token_crypto.py:6-11`.
- Existing CLI: `app/cli/rotate_github_tokens.py`.
- `docs/runbooks/` — no `secret-rotation.md` file.

## Scope

- `docs/runbooks/secret-rotation.md` covering: - `GITHUB_TOKEN_ENCRYPTION_KEY` — Fernet rotation via `MultiFernet`; uses existing CLI. - `JWT_SECRET` — overlap window approach (accept old + new for one cycle). - `BOT_TOKEN` — Telegram BotFather rotation; restart the bot. - `BACKUP_ENCRYPTION_KEY` — restore-impact considerations. - `MCP_FORWARDING_SECRET` (if applicable) and any `OPENROUTER_API_KEY` / `ELEVENLABS_API_KEY` provider keys.
- Each section: rotation steps, zero-downtime overlap window, verification command, blast radius if skipped.
- `.github/ISSUE_TEMPLATE/rotate-secrets-quarterly.md` linked from CLAUDE.md.
- Annual or quarterly cadence reminder; sign-off captured in the runbook.

## Acceptance criteria

- [ ] Runbook published covering every named secret.
- [ ] GitHub issue template added.
- [ ] First drill executed and signed off.
- [ ] CLAUDE.md links the runbook from a "Secrets" section.

## References

- Existing inline doc: `app/security/token_crypto.py:6-11`
- Existing CLI: `app/cli/rotate_github_tokens.py`

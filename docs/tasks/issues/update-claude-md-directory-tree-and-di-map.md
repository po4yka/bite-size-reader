---
title: Update CLAUDE.md directory tree and architecture-overview DI layer map
status: backlog
area: docs
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Update CLAUDE.md directory tree and architecture-overview DI layer map #repo/ratatoskr #area/docs #status/backlog 🔼

## Objective

`CLAUDE.md` "Directory Structure" omits three top-level adapter
packages and underdescribes the `app/api/routers/auth/` package
split. `docs/explanation/architecture-overview.md` lists 5 of the
10 `app/di/` modules, so a contributor wiring a new use case can
miss half the DI surface. Both are read on every onboarding pass
and the drift compounds.

## Context

- `CLAUDE.md:159-186` lists `app/adapters/` subdirs but omits:
  - `app/adapters/ingestors/` (source-ingestor framework)
  - `app/adapters/meta/` (meta adapter)
  - `app/adapters/video/` (video pipeline)
- `CLAUDE.md` line ~178 lists routers flat as
  `(auth, summaries, sync, …)` — `app/api/routers/auth/` is itself
  a package with 15 modules (`endpoints_sessions.py`,
  `endpoints_credentials.py`, `github.py`, etc.) — none mentioned.
- `docs/explanation/architecture-overview.md:260` lists DI modules
  as `api.py, application.py, telegram.py, repositories.py, shared.py`
  but `ls app/di/` shows also `database.py, mcp.py, search.py,
  telegram_commands.py, types.py` — undocumented.

## Scope

- Update `CLAUDE.md` "Directory Structure" tree:
  - Add `ingestors/`, `meta/`, `video/` under `adapters/`.
  - Expand the auth router line to note it is a package and list
    1-2 key modules.
- Update `docs/explanation/architecture-overview.md:260` to include
  all 10 `app/di/` modules, or replace the explicit list with
  "see `ls app/di/`".
- (Optional) Add `tldr_ru` to CLAUDE.md's core-field list in the
  Summary JSON contract summary (it is mandatory for RU output).

## Acceptance criteria

- [ ] `CLAUDE.md` "Directory Structure" matches `ls app/adapters/`
  and `ls app/api/routers/auth/` (sample check).
- [ ] `architecture-overview.md` DI line matches `ls app/di/`.
- [ ] No new doc drift introduced (review for consistency).

## References

- `CLAUDE.md:159-186`
- `docs/explanation/architecture-overview.md:260`
- Audit source: 2026-05-17 inline-TODOs + doc-drift agent

---
title: Replace coverage_includes.txt cherry-pick with full app/ coverage scope
status: backlog
area: testing
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Replace coverage_includes.txt cherry-pick with full app/ coverage scope #repo/ratatoskr #area/testing #status/backlog ⏫

## Objective

CI applies an 80% coverage threshold against ~20 cherry-picked file paths in `tools/scripts/coverage_includes.txt`. New modules added to `app/` without updating this list are silently exempt from the threshold. The 80% target is artificially achievable and does not reflect real coverage of the codebase.

## Context

- `.github/workflows/ci.yml` — coverage threshold check reads `coverage_includes.txt`
- `tools/scripts/coverage_includes.txt` — the inclusion list
- `pyproject.toml` `[tool.coverage.run]` — has `source = ["app"]`

## Acceptance criteria

- [ ] Replace the inclusion list approach with `--source=app --omit=app/db/alembic/*,app/static/*` applied to the full `app/` directory
- [ ] Adjust the threshold if the current test suite does not reach 80% on the full scope (start at actual coverage + 5% buffer, document intent to raise)
- [ ] `coverage_includes.txt` removed or repurposed for reporting only

## Definition of done

Adding a new module to `app/` without tests causes the CI coverage check to fail.

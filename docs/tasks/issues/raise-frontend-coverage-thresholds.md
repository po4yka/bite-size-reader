---
title: Raise frontend coverage thresholds from 8%/5%/5% to 50%/40%/50%
status: backlog
area: testing
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Raise frontend coverage thresholds from 8%/5%/5% to 50%/40%/50% #repo/ratatoskr #area/testing #status/backlog ⏫

## Objective

Frontend coverage thresholds in `vite.config.ts:33-37` are 8% statements / 5% branches / 5% functions. These are effectively meaningless — CI will pass even with almost no test coverage. The 22 existing test files likely already exceed 50% on many modules; raising thresholds enforces regression protection.

## Context

- `clients/web/vite.config.ts:33-37` — `thresholds` config in `coverage` section
- 22 test files currently exist in `clients/web/src/`

## Acceptance criteria

- [ ] Thresholds raised to at least `statements: 50, branches: 40, functions: 50`
- [ ] CI passes with the new thresholds (if actual coverage is below, add missing tests first)
- [ ] New thresholds documented in a comment so contributors know the target

## Definition of done

`npm run test:coverage` passes with the new thresholds and shows actual coverage percentages above the floor.

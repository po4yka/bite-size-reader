---
title: Establish Playwright visual-regression baseline (ratatoskr-web repo)
status: blocked
area: testing
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Establish Playwright visual-regression baseline (ratatoskr-web repo) #repo/ratatoskr #area/testing #status/blocked #blocked 🔼

    - blocked_reason: Work lives in the separate `ratatoskr-web` repository, not in this backend repo. The `ratatoskr-web/` path referenced by the original task spec is not part of this checkout.

## Goal

Finish the migration started in `d4b22a52 ci(web): replace Chromatic with local-only Playwright visual regression`. Without baseline snapshots and an update workflow, visual regression is dormant.

## Where this work belongs

This task targets the frontend repository, **not** this backend repo:

- `ratatoskr-web/playwright.config.ts`
- `ratatoskr-web/tests/playwright/`
- `ratatoskr-web/package.json` scripts
- `ratatoskr-web/.github/workflows/` Playwright job

This repo's `docs/reference/frontend-web.md` documents the contract
from the backend side and may need cross-references once the
baseline-update workflow is finalised in `ratatoskr-web`, but the
snapshot generation, npm script, and CI failure-on-diff work is
implemented in the frontend repo.

## Scope (in the ratatoskr-web repo)

- Generate baseline snapshots for the existing Frost screens and Storybook stories.
- Document the baseline-update workflow (when to run, how to review diffs, how to commit) in `docs/reference/frontend-web.md`.
- Add an npm script `npm run test:visual:update` that updates snapshots locally; CI must never auto-update.
- Decide and document how snapshots are stored (in-repo vs. Git LFS) and the platform/font assumptions.

## Acceptance criteria

- [ ] Baseline snapshots checked in; CI runs visual regression green on a clean checkout.
- [ ] `docs/reference/frontend-web.md` has a Visual Regression section.
- [ ] A deliberate UI tweak in a throwaway branch causes CI to fail with a readable diff.

## References

- Commit d4b22a52 (made in `ratatoskr-web`)
- `ratatoskr-web/` Playwright config
- `docs/reference/frontend-web.md` (this repo) — for cross-references only

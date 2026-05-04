---
title: Establish Playwright visual-regression baseline and update docs
status: backlog
area: testing
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Establish Playwright visual-regression baseline and update docs #repo/ratatoskr #area/testing #status/backlog 🔼

## Goal

Finish the migration started in `d4b22a52 ci(web): replace Chromatic with local-only Playwright visual regression`. Without baseline snapshots and an update workflow, visual regression is dormant.

## Scope

- Generate baseline snapshots for the existing Frost screens and Storybook stories.
- Document the baseline-update workflow (when to run, how to review diffs, how to commit) in `docs/reference/frontend-web.md`.
- Add an npm script `npm run test:visual:update` that updates snapshots locally; CI must never auto-update.
- Decide and document how snapshots are stored (in-repo vs. Git LFS) and the platform/font assumptions.

## Acceptance criteria

- [ ] Baseline snapshots checked in; CI runs visual regression green on a clean checkout.
- [ ] `docs/reference/frontend-web.md` has a Visual Regression section.
- [ ] A deliberate UI tweak in a throwaway branch causes CI to fail with a readable diff.

## References

- Commit d4b22a52
- `clients/web/` Playwright config
- `docs/reference/frontend-web.md`

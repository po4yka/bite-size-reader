---
title: Run Frost Phase 7 mobile regression pass (ratatoskr-web repo)
status: blocked
area: testing
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Run Frost Phase 7 mobile regression pass (ratatoskr-web repo) #repo/ratatoskr #area/testing #status/blocked #blocked 🔼

    - blocked_reason: Work lives in the `ratatoskr-web` frontend repository, not in this backend repo. New spec file path `ratatoskr-web/tests/playwright/mobile-phase7.spec.ts` is not part of this checkout. Also requires real touch hardware for the touch-target verification leg.

## Goal

Prove the mobile rollout shipped in commits 8aa4ec8b..7092000d (Phase 7a–7d, Group A–E) holds up across a real viewport sweep and on touch hardware.

## Where this work belongs

This task targets the frontend repository, **not** this backend repo.
The new spec lives at
`ratatoskr-web/tests/playwright/mobile-phase7.spec.ts` and the
viewport-sweep snapshots under
`ratatoskr-web/tests/playwright/__snapshots__/`.

The touch-target leg (44×44 verification, drawer focus trap, modal
scroll lock) needs real iOS/Android hardware in addition to the
desktop viewport sweep.

## Scope (in the ratatoskr-web repo)

- Playwright mobile spec covering: Library, Articles, Article detail, Search, TagManagement, Collections, Submit, Ingestion, Settings, Dashboard, Automation, Login.
- Viewport sweep: 360, 390, 414, 480, 600, 768 px wide; both portrait and landscape.
- Verify: bottom tab bar visibility, drawer focus trap, 44×44 touch targets, container-query breakpoints, full-screen modal scroll lock.
- File any regressions as child issues; fix obvious ones inline.

## Acceptance criteria

- [ ] New `ratatoskr-web/tests/playwright/mobile-phase7.spec.ts` runs in CI green.
- [ ] Visual snapshots stored under `ratatoskr-web/tests/playwright/__snapshots__/` for each screen × viewport.
- [ ] Defect list captured in the issue or as linked children.

## References

- `ratatoskr-web/`
- `DESIGN.md` (Mobile section)

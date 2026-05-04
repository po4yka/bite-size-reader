---
title: Run Frost Phase 7 mobile regression pass
status: backlog
area: testing
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Run Frost Phase 7 mobile regression pass #repo/ratatoskr #area/testing #status/backlog 🔼

## Goal

Prove the mobile rollout shipped in commits 8aa4ec8b..7092000d (Phase 7a–7d, Group A–E) holds up across a real viewport sweep and on touch hardware.

## Scope

- Playwright mobile spec covering: Library, Articles, Article detail, Search, TagManagement, Collections, Submit, Ingestion, Settings, Dashboard, Automation, Login.
- Viewport sweep: 360, 390, 414, 480, 600, 768 px wide; both portrait and landscape.
- Verify: bottom tab bar visibility, drawer focus trap, 44×44 touch targets, container-query breakpoints, full-screen modal scroll lock.
- File any regressions as child issues; fix obvious ones inline.

## Acceptance criteria

- [ ] New `clients/web/tests/playwright/mobile-phase7.spec.ts` runs in CI green.
- [ ] Visual snapshots stored under `clients/web/tests/playwright/__snapshots__/` for each screen × viewport.
- [ ] Defect list captured in the issue or as linked children.

## References

- `clients/web/`
- `DESIGN.md` (Mobile section)

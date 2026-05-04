---
title: Promote web-playwright-visual to required CI status-check job
status: doing
area: ci
priority: high
owner: Senior Build Gradle CI Engineer
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Promote web-playwright-visual to required CI status-check job #repo/ratatoskr #area/ci #status/doing ⏫

## Context

Related: [[establish-playwright-visual-regression-baseline]].

## Objective

.github/workflows/ci.yml job web-playwright-visual runs the Playwright route + Storybook visual snapshot suite (Frost components, mobile route snapshots across desktop/iPhone 12/Pixel 5/iPad Mini). It is the canonical Frost parity reference for the v1 mobile release. Today it can fail without blocking status-check, which means a Frost regression can ship.

## Expected artifact

- Updated .github/workflows/ci.yml status-check job: web-playwright-visual added to needs and to the success list.
- If the job is too slow for every PR, gate via path filter (clients/web/**, docs/openapi/mobile_api.yaml, .github/workflows/ci.yml) but still block status-check when it runs.

## Definition of done

A PR that breaks a committed Playwright snapshot fails the merge gate.

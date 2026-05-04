---
title: Fix GitHub Actions version tags referencing non-existent versions
status: backlog
area: ci
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Fix GitHub Actions version tags referencing non-existent versions #repo/ratatoskr #area/ci #status/backlog ⏫

## Objective

`.github/workflows/ci.yml` references action versions that do not exist: `actions/checkout@v6`, `actions/setup-python@v6`, `actions/setup-node@v6`, `actions/upload-artifact@v7`, `actions/download-artifact@v8`. Latest stable versions are all v4. The CI pipeline may be broken or relying on non-standard forks.

## Context

- `.github/workflows/ci.yml` — multiple jobs affected
- Latest published: `actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`, `actions/upload-artifact@v4`, `actions/download-artifact@v4`

## Acceptance criteria

- [ ] All action references updated to current stable versions
- [ ] CI pipeline passes end-to-end after the update
- [ ] Pin each action to its SHA for supply-chain safety (optional but recommended)

## Definition of done

CI green on a test push with no "action not found" errors.

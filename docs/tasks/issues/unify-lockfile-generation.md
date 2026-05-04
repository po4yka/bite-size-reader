---
title: Unify uv pip compile vs uv export usage between update-locks.yml and CI prepare step
status: backlog
area: ci
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Unify uv pip compile vs uv export usage between update-locks.yml and CI prepare step #repo/ratatoskr #area/ci #status/backlog 🔽

## Objective

`update-locks.yml` uses `uv pip compile` to generate `requirements.txt` while the CI `prepare-environment` job uses `uv export`. These are different commands with different resolution strategies (compile resolves from scratch; export reads the lockfile). This mismatch is the root cause of false lockfile-drift alerts and CI failures when the two produce different output.

## Context

- `.github/workflows/update-locks.yml` — uses `uv pip compile`
- `.github/workflows/ci.yml` `prepare-environment` job — uses `uv export`
- `Makefile` `lock-uv` target — also uses `uv export`

## Acceptance criteria

- [ ] Both `update-locks.yml` and `ci.yml` use identical commands to generate requirements files
- [ ] `Makefile lock-uv` target uses the same command
- [ ] The lockfile drift detection in CI produces no false positives after unification

## Definition of done

Running `make lock-uv` locally and pushing the result causes no drift warning in CI.

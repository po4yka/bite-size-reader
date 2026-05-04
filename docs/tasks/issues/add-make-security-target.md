---
title: Add make security target grouping bandit and pip-audit for local security scanning
status: backlog
area: ops
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Add make security target grouping bandit and pip-audit for local security scanning #repo/ratatoskr #area/ops #status/backlog 🔽

## Objective

`bandit` and `pip-audit` run only in CI. Developers have no easy way to run security checks locally before pushing. A `make security` target brings CI-parity to local development.

## Context

- `Makefile` — no security-related targets exist
- CI runs: `bandit -r app -ll` and `pip-audit --strict`
- Both tools are not in `requirements-dev.txt` (installed ad-hoc in CI)

## Acceptance criteria

- [ ] `make security` target runs `bandit -r app -ll` and `pip-audit`
- [ ] `bandit` and `pip-audit` added to the `dev` dependency group in `pyproject.toml` so they are available after `make setup-dev`
- [ ] `make all` optionally includes `security` or documents that it does not

## Definition of done

`make setup-dev && make security` runs without "command not found" errors on a fresh checkout.

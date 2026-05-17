---
title: Add `make bootstrap` and demo seed-data target for new contributors
status: backlog
area: ops
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add `make bootstrap` and demo seed-data target for new contributors #repo/ratatoskr #area/ops #status/backlog 🔽

## Objective

`Makefile` has `setup-dev` (line 65: `uv sync` + pre-commit) but
nothing brings up Postgres + Redis + Qdrant locally, runs
migrations, and seeds a test user / allowlist. New contributors
must read `docs/guides/deploy-production.md` and ~5 other docs to
get started. Slow onboarding discourages outside contributors
and slows new-engineer ramp.

## Context

- `Makefile:65` — `setup-dev` target (Python deps only).
- `tools/scripts/` — no `seed*` or `bootstrap*` script.
- Compose dev overlay:
  `ops/docker/docker-compose.dev.yml` (exists per CLAUDE.md).

## Scope

- `make bootstrap` target that:
  - Brings up `postgres`, `redis`, `qdrant` via the dev compose
    overlay.
  - Waits for health checks.
  - Runs `python -m app.cli.migrate_db`.
  - Seeds an `ALLOWED_USER_IDS` test user + a couple of fake
    summaries.
  - Prints a CLI runner example URL and the URLs for Grafana,
    Postgres adminer, etc.
- Optional `make seed-demo-data` loads ~10 sample summaries for
  UI / API exploration.
- Optional `make teardown-dev` cleans the local compose state.
- Update `CONTRIBUTING.md` (or `CLAUDE.md`) "Quickstart" with
  the new commands.

## Acceptance criteria

- [ ] `git clone … && make bootstrap` produces a working dev
  environment in < 5 minutes.
- [ ] `make seed-demo-data` produces a non-empty library view.
- [ ] `make teardown-dev` cleans up cleanly.

## References

- `Makefile:65`
- Dev compose (per CLAUDE.md):
  `ops/docker/docker-compose.dev.yml`
- Migration CLI: `app/cli/migrate_db.py`

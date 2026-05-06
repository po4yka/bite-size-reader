---
title: Add Postgres service to docker-compose
status: backlog
area: ops
priority: high
owner: Nikita Pochaev
blocks:
  - migrate-postgres-build-data-migrator
  - migrate-postgres-write-pi-runbook
blocked_by:
  - migrate-postgres-decide-deployment-topology
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Add Postgres service to docker-compose #repo/ratatoskr #area/ops #status/backlog ⏫

## Objective

Wire Postgres into local and Pi compose so `ratatoskr-bot` and `ratatoskr-mobile-api`
can connect to it via `DATABASE_URL` (asyncpg DSN form).

## Context

D1 confirmed: dedicated `ratatoskr-postgres` container. Required additions to
`ops/docker/docker-compose.yml`:

- New `postgres` service: image `postgres:16-alpine`, container name
  `ratatoskr-postgres`, named volume `ratatoskr_postgres_data`, healthcheck
  `pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB`, resource limits (256 MiB
  reservation, 1 GiB limit, 0.10–0.50 CPU).
- Env: `POSTGRES_DB=ratatoskr`, `POSTGRES_USER=ratatoskr_app`,
  `POSTGRES_PASSWORD=${POSTGRES_PASSWORD}` (required, no default).
- `ratatoskr` and `mobile-api` services gain
  `DATABASE_URL=postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr`
  and `depends_on: postgres: condition: service_healthy`.
- Healthcheck commands for `ratatoskr` and `mobile-api` change from
  `sqlite3.connect(...)` (lines 58, 141) to `python -m app.cli.healthcheck`
  (added in O2 / port-raw-sql-helpers).
- The `/data` volume mount stays — used by video downloads, audio generation
  artefacts, etc. Only the SQLite file is gone.
- Pi overlay (`docker-compose.pi.yml`): no Postgres-specific override needed —
  the dedicated container runs on the Pi like any other service.

## Acceptance criteria

- [ ] `docker compose -f ops/docker/docker-compose.yml up -d postgres` boots a
      healthy Postgres on the developer laptop.
- [ ] With `DATABASE_URL` set in `.env`, `ratatoskr` and `mobile-api` services start
      and pass their healthchecks (which become DSN-aware in O3).
- [ ] No `DB_PATH` volume mount remains for Postgres deployments (the `/data` mount
      stays for video downloads and other artefacts; only the SQLite file is gone).
- [ ] `.env.example` documents `DATABASE_URL` and `POSTGRES_PASSWORD` with empty
      defaults and a comment explaining the required format.
- [ ] Pi overlay file is updated per D1 decision; both code paths render valid YAML
      (`docker compose config` exits 0).

## Notes

`postgres:16-alpine` ships aarch64. Do not use `postgres:16` (Debian-based, ~2× the
image size with no relevant features for this workload).

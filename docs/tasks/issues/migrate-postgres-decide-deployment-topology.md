---
title: Decide Postgres deployment topology on raspi
status: done
area: ops
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-add-compose-service
  - migrate-postgres-write-pi-runbook
  - migrate-postgres-execute-pi-cutover
blocked_by: []
created: 2026-05-06
updated: 2026-05-06
---

- [x] #task Decide Postgres deployment topology on raspi #repo/ratatoskr #area/ops #status/done 🔺 ✅ 2026-05-06

## Objective

Pick the Postgres host topology for the `raspi` deployment and lock it into the
migration plan. This blocks the compose work, runbook, and cutover.

## Context

The Pi already runs a `shared-postgres` container (visible in `docker ps` output during
plan exploration). Two viable options:

- **A.** Reuse `shared-postgres`: create a `ratatoskr` database and `ratatoskr_app` role
  inside that instance. No new container.
- **B.** Add a dedicated `ratatoskr-postgres` service to
  `ops/docker/docker-compose.yml` with its own named volume and resource limits.

Plan default: **B**, on the grounds of independent lifecycle and backups. Option A is
trivial to fall back to via `DATABASE_URL`.

See `docs/tasks/migrate-sqlite-to-postgresql-plan.md` § "Pi deployment topology" for the
trade-off table.

## Acceptance criteria

- [ ] Owner decision recorded in this issue's "Decision" section.
- [ ] Decision references concrete `DATABASE_URL` shape (host, port, db name, role).
- [ ] If A is chosen: confirm naming convention for the `ratatoskr` DB inside
      `shared-postgres` (db, role, schema).
- [ ] If B is chosen: confirm Postgres major version (default: 16), volume name, and
      resource budget (default: 256 MiB RAM reservation, 1 GiB limit).

## Decision

**Dedicated `ratatoskr-postgres` container** (option B) — confirmed 2026-05-06.

- Image: `postgres:16-alpine` (aarch64 native).
- Service name in `ops/docker/docker-compose.yml`: `postgres` (network alias
  `ratatoskr-postgres`).
- Database: `ratatoskr`. Role: `ratatoskr_app`.
- Volume: `ratatoskr_postgres_data` (named, persisted).
- Resource budget: 256 MiB reservation, 1 GiB limit; 0.10–0.50 CPU.
- DSN consumed by app: `postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr`.
- The existing `shared-postgres` container is **not** used; isolation prefers a
  dedicated lifecycle and backup cadence.

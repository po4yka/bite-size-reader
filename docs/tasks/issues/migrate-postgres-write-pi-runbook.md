---
title: Write Pi Postgres cutover runbook
status: backlog
area: ops
priority: high
owner: Nikita Pochaev
blocks:
  - migrate-postgres-execute-pi-cutover
blocked_by:
  - migrate-postgres-decide-deployment-topology
  - migrate-postgres-build-data-migrator
  - migrate-postgres-add-compose-service
  - migrate-postgres-add-test-fixtures-and-ci
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Write Pi Postgres cutover runbook #repo/ratatoskr #area/ops #status/backlog ⏫

## Objective

Author `docs/runbooks/pi-postgres-cutover.md` — a step-by-step runbook for migrating
the live `raspi` deployment from SQLite + Peewee to Postgres + SQLAlchemy 2.0,
with a tested image-revert rollback path.

## Context

Pi state captured during planning:

- Repo path: `/home/po4yka/ratatoskr` (user `po4yka`).
- Containers running today: `ratatoskr-bot`, `ratatoskr-mobile-api`, `shared-postgres`,
  `ratatoskr-chroma`, `ratatoskr-redis`.
- DB file: `/home/po4yka/ratatoskr/data/ratatoskr.db` (498 MB).
- Disk: 234 GB total, 198 GB free.
- `ssh raspi` is the access path.

**Critical**: because Peewee and SQLAlchemy are mutually exclusive in code,
rollback requires reverting both image and env. The runbook must produce two
named images before the window opens:

- `ratatoskr:pre-sqlalchemy` — last green commit before any of F3/M*/R* land.
  Tagged from CI on the merge train commit immediately before F3.
- `ratatoskr:post-sqlalchemy` — the head of `main` once R3 + T3 are green.

Both images must be present on the Pi before C2 starts (`docker pull`).

Runbook outline (each section with concrete commands, expected output, and a "what
to do if this fails" branch):

1. **Pre-flight** (T-24h): announce window, build and push both images,
   `docker pull` them on the Pi, snapshot the SQLite file, dry-run ETL on a
   copy locally, verify CI is green on `main`.
2. **Window open**: `docker compose stop ratatoskr mobile-api` on Pi.
3. **Backup**: `cp data/ratatoskr.db data/ratatoskr.db.pre-pg-$(date +%F)` on Pi.
4. **Bring up Postgres**: `docker compose up -d postgres`. Wait for healthy.
5. **Schema bootstrap**: `docker compose run --rm ratatoskr python -m
   app.cli.migrate_db` (runs `alembic upgrade head` against the new Postgres).
6. **Data migration**: `docker compose run --rm ratatoskr python -m
   app.cli.migrate_sqlite_to_postgres --source-sqlite /data/ratatoskr.db
   --target-postgres "$DATABASE_URL"`. Capture the validation report.
7. **Validation**: rerun the migrator with `--dry-run` on the target — zero
   pending rows. Run `python -m app.cli.healthcheck`. Smoke
   `curl http://localhost:18000/health`.
8. **Flip env**: edit `.env` to set `DATABASE_URL` and `POSTGRES_PASSWORD`;
   remove `DB_PATH` (the legacy var is no longer read once on Postgres).
9. **Restart**: `docker compose up -d ratatoskr mobile-api`. Watch logs for 30
   minutes.
10. **Post-cutover** (T+24h): take first `pg_dump`; verify topic search and
    basic summary creation through Telegram; mark SQLite file read-only with
    `chmod a-w data/ratatoskr.db.pre-pg-*`.
11. **Rollback**: `docker compose stop ratatoskr mobile-api`, retag image
    (`docker tag ratatoskr:pre-sqlalchemy ratatoskr:latest`), restore
    `data/ratatoskr.db.pre-pg-<date>`, unset `DATABASE_URL`, restart compose.
    Postgres data stays in its volume for a future re-attempt.

## Acceptance criteria

- [ ] `docs/runbooks/pi-postgres-cutover.md` exists with all 11 sections, each
      containing the exact commands and expected output.
- [ ] Both `ratatoskr:pre-sqlalchemy` and `ratatoskr:post-sqlalchemy` images
      are built, pushed, and pulled to the Pi before the window opens.
- [ ] Runbook is dry-run twice on a developer laptop (against a local Pi-DB
      copy and a local Postgres container) before being marked ready.
- [ ] The dry-run results (timings, anomalies) are appended to the runbook.
- [ ] Rollback is dry-run once on the laptop using image-revert + env-revert;
      recovery time is recorded.
- [ ] Maintenance window length estimate (with one σ buffer) is on the
      runbook front matter.
- [ ] Linked from `docs/SPEC.md` "Operations" section.

## Notes

The image-revert path is the new wrinkle vs. a driver-only swap: rolling back
the Peewee→SQLAlchemy port purely via env is impossible because the model code
itself changed. Confirm during dry-run that `docker tag` + `docker compose up
-d` on the Pi reverts cleanly with a stale image already present.

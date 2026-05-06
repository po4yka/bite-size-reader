---
title: Execute Pi Postgres cutover
status: backlog
area: ops
priority: critical
owner: Nikita Pochaev
blocks:
  - migrate-postgres-update-docs
blocked_by:
  - migrate-postgres-write-pi-runbook
created: 2026-05-06
updated: 2026-05-06
---

- [ ] #task Execute Pi Postgres cutover #repo/ratatoskr #area/ops #status/backlog 🔺

## Objective

Owner-driven execution of the cutover runbook on `raspi`. End state: bot and
mobile-api run against PostgreSQL via SQLAlchemy 2.0 in production, every row
from the pre-cutover SQLite snapshot is reachable, and the bot has been observed
healthy for ≥ 24 hours.

## Context

This is the live execution task — the runbook (C1) is the script. Owner runs it
via `ssh raspi`. Prerequisites that must be merged to `main` and present in the
`ratatoskr:post-sqlalchemy` image before the window opens: F1, F2, F3, M1–M4,
R1–R3, O2 (raw-SQL), O5 (alembic env), T1 (compose), T2 (migrator), T3 (CI).

Both images (`pre-sqlalchemy` and `post-sqlalchemy`) must be pulled to the Pi
before C2 starts. If C2 fails mid-way and the runbook's rollback path is
exercised, the SQLite-era image must already be local — pulling during an
incident is the wrong time.

## Acceptance criteria

- [ ] Maintenance window is announced and held; total downtime recorded.
- [ ] Each runbook step is checked off live, with output captured to
      `docs/runbooks/cutover-log-YYYY-MM-DD.md`.
- [ ] Post-cutover smoke covers: `/health`, sending a real article URL via
      Telegram and getting a summary, topic search returning results, mobile
      API auth flow.
- [ ] No `database is locked` events for 24h in logs (metric on Postgres
      should be structurally zero).
- [ ] No Peewee or SQLite import is exercised in 24h (grep
      `peewee|RowSqliteDatabase|playhouse` in logs; expected zero).
- [ ] First `pg_dump` taken and stored under
      `/home/po4yka/ratatoskr/backups/`.
- [ ] Cutover-log file committed back to the repo for permanent record.
- [ ] If anything goes wrong, rollback is executed per runbook §11
      (image-revert + env-revert + SQLite restore); this issue is reopened with
      the diagnosis.

## Notes

Do **not** execute this task automatically from CI or an automation. Owner must be
at the keyboard and able to abort. The runbook explicitly forbids `--no-verify` style
shortcuts.

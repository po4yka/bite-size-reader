---
title: Add automated Postgres backups with retention and freshness alert
status: backlog
area: ops
priority: critical
owner: unassigned
blocks:
  - add-dr-restore-drill-and-runbook
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add automated Postgres backups with retention and freshness alert #repo/ratatoskr #area/ops #status/backlog 🔺

## Objective

`docs/guides/backup-and-restore.md:140-161` documents only **manual** `pg_dump` commands. There is no cron job, no systemd timer, no Taskiq job, and no backup sidecar in `ops/docker/docker-compose.yml`. `UserBackup` exports are user-triggered and only cover the user's own data — they are not an operator-side DB backup. A Pi SD-card failure or `ratatoskr_postgres_data` volume corruption destroys all summaries, requests, refresh-token families, and digest history with no recovery path.

## Context

- Manual procedure: `docs/guides/backup-and-restore.md:140-161`.
- Compose definition: `ops/docker/docker-compose.yml:890-921` declares `postgres` with no backup sidecar.
- No `pgbackrest`, `wal-g`, or `backup` service anywhere in `ops/`.
- `Makefile` has no `backup` target.
- The only backup-related router (`app/api/routers/backups.py`) is user-triggered `UserBackup` exports — not operator-side DB backups.

## Scope

- Add a `pg-backup` service to `ops/docker/docker-compose.yml` (sidecar container OR Taskiq job in the existing worker) that: - Runs `pg_dump --format=custom` on a configurable cron (default `0 3 * * *` UTC, ie 03:00 UTC daily). - Writes to a host-mounted volume with N-day retention (default 14). - Encrypts at rest if `BACKUP_ENCRYPTION_KEY` is set. - Optionally uploads to S3 / Backblaze via env vars (`BACKUP_S3_BUCKET`, `BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY`).
- New Prometheus metric `ratatoskr_pg_backup_last_success_timestamp_seconds`.
- Alert when stale > 36h → severity critical.
- Document in `docs/guides/backup-and-restore.md` and add a `BACKUP_*` block to `docs/reference/environment-variables.md`.

## Acceptance criteria

- [ ] Daily backup runs without operator intervention.
- [ ] Backup metadata file lists timestamp + size + sha256.
- [ ] Restore path validated (covered by [[add-dr-restore-drill-and-runbook]]).
- [ ] Freshness metric + alert wired.

## References

- Existing manual procedure: `docs/guides/backup-and-restore.md:140-161`
- Compose: `ops/docker/docker-compose.yml:890-921`
- Related: [[add-dr-restore-drill-and-runbook]]

---
title: Add disaster-recovery runbook with tested quarterly restore drill
status: backlog
area: ops
priority: high
owner: unassigned
blocks: []
blocked_by:
  - add-automated-postgres-backups
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add disaster-recovery runbook with tested quarterly restore drill #repo/ratatoskr #area/ops #status/backlog ⏫

## Objective

`docs/runbooks/` contains only `pi-postgres-cutover.md`; no `disaster-recovery.md`, no RTO/RPO targets, no restore drill. `docs/guides/backup-and-restore.md:459` says "restore the newest verified pg_dump archive" but "verified" is never operationalized. Untested backups routinely fail at restore time (encryption-key drift, schema-version mismatch, missing extensions). An RPO/RTO of "unknown" is not a recovery posture.

## Context

- `docs/runbooks/` — single file present.
- Vague restore instruction: `docs/guides/backup-and-restore.md:459`.
- Three datastores in play: Postgres (primary), Qdrant (vectors), Redis (cache + AOF for digest session state).
- Blocked by [[add-automated-postgres-backups]] — there must be a scheduled backup to restore *from* before the drill matters.

## Scope

- `docs/runbooks/disaster-recovery.md` with: - Declared RTO + RPO targets (e.g. RTO 1h, RPO 24h). - Per-datastore restore procedure (Postgres, Qdrant, Redis AOF). - Verification checklist (row counts, latest summary timestamp, Qdrant collection sizes, redis key sample). - Communication template ("notify the user the bot is down").
- CI smoke job: load a sample `pg_dump` archive into an ephemeral Postgres + run `alembic upgrade head` — catches schema/dump drift early.
- Quarterly drill checklist (GitHub issue template); sign-off recorded in the runbook.
- Backup-encryption-key rotation step that survives an in-flight restore.

## Acceptance criteria

- [ ] Runbook published with RTO/RPO and step-by-step restore.
- [ ] CI job loads a sample dump and runs migrations on every PR that touches `app/db/`.
- [ ] First drill executed and signed off.
- [ ] Drill template added to `.github/ISSUE_TEMPLATE/`.

## References

- Existing runbook: `docs/runbooks/pi-postgres-cutover.md`
- Backup guide: `docs/guides/backup-and-restore.md:459`
- Depends on: [[add-automated-postgres-backups]]

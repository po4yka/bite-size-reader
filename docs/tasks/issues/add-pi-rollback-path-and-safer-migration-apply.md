---
title: Add Pi deploy rollback path and gate Alembic migrations behind an explicit apply step
status: backlog
area: ops
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add Pi deploy rollback path and gate Alembic migrations behind an explicit apply step #repo/ratatoskr #area/ops #status/backlog ⏫

## Objective

`tools/scripts/build-and-deploy-pi.sh` streams a new image and recreates the service container with no rollback path; a previous image tag is not retained. Meanwhile `ops/docker/docker-compose.yml:2-21` auto-runs `python -m app.cli.migrate_db` (= `alembic upgrade head`) on every `migrate` service start with `depends_on: service_completed_successfully` blocking app start. A buggy migration takes the whole stack down atomically with no fast recovery — the deploy guide's only remediation is "restore the backup tarball", which is destructive and slow.

## Context

- Deploy script: `tools/scripts/build-and-deploy-pi.sh:153` — `up -d --no-deps --force-recreate ${SERVICE}`, no `--rollback`.
- Compose `migrate` service: `ops/docker/docker-compose.yml:2-21` (auto-upgrade), `:100-102` (blocks app start).
- Deploy guide remediation: `docs/guides/deploy-production.md:416-419`.

## Scope

- **Rollback:** - In `build-and-deploy-pi.sh`, before `--force-recreate`, tag the currently-running image as `<svc>:previous`. - Add `--rollback` flag that flips `<svc>:latest` ↔ `<svc>:previous` and re-creates the container. - Emit `ratatoskr_deploy_version_info{git_sha, deployed_at}` Prometheus gauge so rollbacks are visible in Grafana.
- **Migration safety:** - Move `migrate_db` invocation out of automatic container start. - Add `make pi-migrate` step that runs Alembic apply behind a `--apply` flag; default is dry-run (`alembic upgrade head --sql`). - Container start checks `alembic current` against `alembic heads`; refuses to start if mismatched (clean fail vs running against the wrong schema).
- Update `docs/guides/deploy-production.md` with new sequence: `make pi-deploy` → `make pi-migrate --apply` → app start.

## Acceptance criteria

- [ ] Failed deploy can be rolled back in < 60 seconds via one command.
- [ ] Bad migration does not block app restart; the operator must consciously apply it.
- [ ] Grafana shows current and previous deploy SHAs.
- [ ] Updated deploy guide documents the new flow.

## References

- Deploy script: `tools/scripts/build-and-deploy-pi.sh:153`
- Compose: `ops/docker/docker-compose.yml:2-21, :100-102`
- Deploy guide: `docs/guides/deploy-production.md:416-419`

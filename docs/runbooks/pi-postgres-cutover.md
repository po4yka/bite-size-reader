---
title: Pi SQLite to Postgres cutover runbook
status: draft (operational dry-runs pending)
maintenance_window_estimate: 60 min nominal · 90 min with one-σ buffer (refine after dry-run)
last_updated: 2026-05-06
---

# Pi SQLite to Postgres cutover runbook

This runbook covers the one-shot migration of the live `raspi` deployment
from SQLite + Peewee to PostgreSQL + SQLAlchemy 2.0. Read it end-to-end
before opening the maintenance window — the rollback path requires both
images to already be on the Pi, so prep is not optional.

> **Status: draft.** Sections marked **`[VERIFY]`** must be exercised in a
> dry-run on a developer laptop before this runbook is considered ready
> for production. Dry-run results (timings, anomalies, deltas) are
> recorded in [Appendix A](#appendix-a--dry-run-log).

## Pi state at time of writing

| Item | Value |
|---|---|
| Repo path | `/home/po4yka/ratatoskr` |
| User | `po4yka` |
| Containers running today | `ratatoskr-bot`, `ratatoskr-mobile-api`, `shared-postgres`, `ratatoskr-chroma`, `ratatoskr-redis` |
| Active SQLite file | `/home/po4yka/ratatoskr/data/ratatoskr.db` (≈ 498 MB) |
| Disk | 234 GB total, 198 GB free |
| Access path | `ssh raspi` |

## Why image-revert is required

Peewee and SQLAlchemy are mutually exclusive in code. A pure env-revert
(`unset DATABASE_URL`, `restart`) cannot work because the application
modules themselves no longer import Peewee. Rollback therefore requires
both:

1. an **image revert** to the last green pre-port image (`ratatoskr:pre-sqlalchemy`),
2. an **env revert** that restores `DB_PATH` and removes `DATABASE_URL`.

Both images must be present on the Pi via `docker pull` before the
window opens.

---

## 1. Pre-flight (T-24h)

**Goal:** lock down the inputs so the cutover window only contains
mechanical steps.

```bash
# On a developer laptop, in the ratatoskr repo:

# 1.1 Confirm CI is green on main and the relevant tags exist.
git fetch --tags origin
git tag -l 'pre-sqlalchemy*' 'post-sqlalchemy*'

# 1.2 Build and push both images (replace registry with the actual one).
git checkout pre-sqlalchemy
make pi-build-only IMAGE_TAG=pre-sqlalchemy SERVICE=ratatoskr
make pi-build-only IMAGE_TAG=pre-sqlalchemy SERVICE=mobile-api

git checkout post-sqlalchemy   # head of main once R3 + T3 are green
make pi-build-only IMAGE_TAG=post-sqlalchemy SERVICE=ratatoskr
make pi-build-only IMAGE_TAG=post-sqlalchemy SERVICE=mobile-api

# 1.3 Pull both tags on the Pi.
ssh raspi "cd ratatoskr && \
  docker pull ratatoskr:pre-sqlalchemy && \
  docker pull ratatoskr:post-sqlalchemy && \
  docker pull mobile-api:pre-sqlalchemy && \
  docker pull mobile-api:post-sqlalchemy && \
  docker images | grep -E 'ratatoskr|mobile-api'"

# 1.4 Snapshot the live SQLite file to the laptop.
ssh raspi 'sqlite3 /home/po4yka/ratatoskr/data/ratatoskr.db ".backup /tmp/ratatoskr.snapshot.db"'
scp raspi:/tmp/ratatoskr.snapshot.db ./tmp/ratatoskr.snapshot.db

# 1.5 Dry-run ETL locally against a fresh local Postgres + the snapshot.
docker compose -f ops/docker/docker-compose.yml up -d postgres
DATABASE_URL="postgresql+asyncpg://ratatoskr_app:devpw@localhost:5432/ratatoskr" \
  python -m app.cli.migrate_db
DATABASE_URL="postgresql+asyncpg://ratatoskr_app:devpw@localhost:5432/ratatoskr" \
  python -m app.cli.migrate_sqlite_to_postgres \
    --source-sqlite ./tmp/ratatoskr.snapshot.db \
    --target-postgres "$DATABASE_URL" \
    --dry-run
# Then run for real and capture the validation report:
DATABASE_URL="postgresql+asyncpg://ratatoskr_app:devpw@localhost:5432/ratatoskr" \
  python -m app.cli.migrate_sqlite_to_postgres \
    --source-sqlite ./tmp/ratatoskr.snapshot.db \
    --target-postgres "$DATABASE_URL" \
  | tee tmp/etl-dry-run-$(date +%F).log
```

**Expected:** ETL exit code 0; validation report shows zero count
mismatches; topic-search row count matches `(SELECT COUNT(*) FROM
requests WHERE …)`.

**If this fails:** do NOT open the window. Triage offline first.

---

## 2. Open the window

```bash
ssh raspi 'cd ratatoskr && docker compose stop ratatoskr mobile-api'
```

**Expected:** both containers transition to `Exit 0` within ~5 s. Verify
via `docker compose ps`.

**If this fails:** force-stop with `docker compose kill ratatoskr
mobile-api`. The bot does not write to SQLite during shutdown beyond
flushing the WAL — `kill` is recoverable.

---

## 3. Backup the SQLite file

```bash
ssh raspi 'cd ratatoskr && \
  cp data/ratatoskr.db data/ratatoskr.db.pre-pg-$(date +%F) && \
  ls -lh data/ratatoskr.db data/ratatoskr.db.pre-pg-*'
```

**Expected:** the new copy exists and is the same size as the original
(within a few KB). The original is left in place for the rollback path.

**If this fails (out of disk):** abort and reclaim space. Do not proceed
without a backup.

---

## 4. Bring up Postgres

```bash
ssh raspi 'cd ratatoskr && \
  docker compose -f ops/docker/docker-compose.yml \
                 -f ops/docker/docker-compose.pi.yml \
    up -d postgres'

# Wait for healthy (poll up to 60 s):
ssh raspi 'cd ratatoskr && \
  for i in {1..30}; do
    docker inspect --format="{{.State.Health.Status}}" ratatoskr-postgres
    sleep 2
  done | tail -5'
```

**Expected:** `healthy` within ~10 s (the named volume already exists
from a prior dev/dry-run, so first-boot init is skipped on the Pi if the
volume was preseeded; if not, allow ~30 s for `initdb`).

**If this fails:** check `docker logs ratatoskr-postgres`. Common cause:
`POSTGRES_PASSWORD` missing in `.env`. Set it and retry step 4.

---

## 5. Schema bootstrap (Alembic)

```bash
ssh raspi 'cd ratatoskr && \
  docker compose run --rm \
    -e DATABASE_URL="postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr" \
    ratatoskr python -m app.cli.migrate_db'
```

**Expected:** Alembic prints `Running upgrade … -> 0001_baseline_sqlalchemy`
(or the current head). Exit code 0.

**If this fails:** any non-zero exit is fatal. Capture the full log,
investigate offline, do **NOT** proceed to step 6 — running the ETL
against an incomplete schema corrupts the migration.

---

## 6. Data migration

```bash
ssh raspi 'cd ratatoskr && \
  docker compose run --rm \
    -e DATABASE_URL="postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr" \
    ratatoskr python -m app.cli.migrate_sqlite_to_postgres \
      --source-sqlite /data/ratatoskr.db \
      --target-postgres "$DATABASE_URL" \
  | tee /home/po4yka/ratatoskr/logs/etl-cutover-$(date +%F).log'
```

**Expected:** the final report shows:

- per-table source/target counts in lockstep,
- zero mismatches,
- sequence values populated for every autoincrement table,
- topic-search rebuild row count > 0 (or 0 only if there are no requests).

**Wall-clock estimate:** the laptop dry-run (498 MB snapshot) measured
**`[VERIFY]`** seconds; the Pi is roughly 3-4× slower for this workload,
so budget **`[VERIFY]`** minutes.

**If this fails:** the Postgres database is now in an inconsistent
state. Two options:

1. **Reset Postgres and retry**: `docker compose stop postgres && docker
   volume rm ratatoskr_postgres_data && docker compose up -d postgres`,
   then retry from step 5.
2. **Roll back to SQLite**: jump to [Section 11](#11-rollback).

Do not attempt manual Postgres surgery during the window.

---

## 7. Validation

```bash
# 7.1 Re-run the migrator in --dry-run mode against the now-loaded target.
ssh raspi 'cd ratatoskr && \
  docker compose run --rm \
    -e DATABASE_URL="postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr" \
    ratatoskr python -m app.cli.migrate_sqlite_to_postgres \
      --source-sqlite /data/ratatoskr.db \
      --target-postgres "$DATABASE_URL" \
      --dry-run'

# 7.2 Healthcheck.
ssh raspi 'cd ratatoskr && \
  docker compose run --rm \
    -e DATABASE_URL="postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr" \
    ratatoskr python -m app.cli.healthcheck'
```

**Expected:** dry-run reports zero pending rows (everything already in
target). Healthcheck exits 0.

**If this fails:** dry-run mismatches mean the live data drifted between
backup and migration (unlikely if step 2 succeeded). Roll back.

---

## 8. Flip env

```bash
ssh raspi 'cd ratatoskr && \
  cp .env .env.pre-pg-$(date +%F) && \
  # Add DATABASE_URL and POSTGRES_PASSWORD if not already present:
  grep -q "^DATABASE_URL=" .env || echo "DATABASE_URL=postgresql+asyncpg://ratatoskr_app:${POSTGRES_PASSWORD}@postgres:5432/ratatoskr" >> .env && \
  grep -q "^POSTGRES_PASSWORD=" .env || echo "POSTGRES_PASSWORD=<paste real password>" >> .env && \
  # Comment out DB_PATH so any legacy reader fails loudly:
  sed -i.bak "s|^DB_PATH=|# DB_PATH (deprecated post-cutover)=|g" .env'
```

**Expected:** `.env.pre-pg-<date>` exists; `.env` contains
`DATABASE_URL` and `POSTGRES_PASSWORD`; `DB_PATH` is commented out.

**If this fails (typo, missing var):** roll back env edits via the
`.env.pre-pg-<date>` snapshot; re-do this section.

---

## 9. Restart

```bash
ssh raspi 'cd ratatoskr && \
  docker compose -f ops/docker/docker-compose.yml \
                 -f ops/docker/docker-compose.pi.yml \
    up -d ratatoskr mobile-api'

# Tail logs for 30 minutes (in two windows):
ssh raspi 'cd ratatoskr && docker compose logs -f --tail=200 ratatoskr'
ssh raspi 'cd ratatoskr && docker compose logs -f --tail=200 mobile-api'
```

**Expected:**

- both containers transition to `healthy` within 60 s,
- bot log shows `telethon_session_resumed` and a successful Postgres
  healthcheck within the first minute,
- mobile-api log shows the lifespan startup sequence and a successful
  `/health` self-check,
- no `database is locked`, `OperationalError`, `IntegrityError`, or
  `database_proxy` traceback in the first 10 minutes.

**If this fails:** stop the containers and roll back
([Section 11](#11-rollback)). Do not attempt forward repairs in the
window.

---

## 10. Post-cutover (T+24h)

```bash
# 10.1 First post-cutover pg_dump backup.
ssh raspi 'cd ratatoskr && \
  docker compose exec -T postgres \
    pg_dump -U ratatoskr_app -F c -d ratatoskr \
      > /home/po4yka/ratatoskr/backups/ratatoskr-$(date +%F).dump'

# 10.2 Topic-search smoke check (a known-result query).
# (Use the bot or MCP catalog endpoint; document the canonical query inline
# here once it has been picked.)

# 10.3 Mark the SQLite backup read-only so nothing mutates it.
ssh raspi 'chmod a-w /home/po4yka/ratatoskr/data/ratatoskr.db.pre-pg-*'

# 10.4 Confirm the legacy file is no longer being written:
ssh raspi 'ls -lh /home/po4yka/ratatoskr/data/ratatoskr.db'
# (The mtime should match the moment of step 3.)
```

**Expected:** `pg_dump` produces a non-empty `.dump` file; topic search
returns sensible results; the legacy SQLite file's mtime matches the
backup time, confirming nothing wrote to it post-cutover.

The legacy SQLite file stays on disk for ≥ 7 days as a hot rollback
target. After 7 incident-free days it can be moved to
`/home/po4yka/ratatoskr/backups/sqlite-archive/` and after 30 days
deleted (per L1 task).

---

## 11. Rollback

Use this path if anything between sections 4 and 10 produces unrecoverable
errors.

```bash
ssh raspi 'cd ratatoskr && \
  # 11.1 Stop the new images.
  docker compose stop ratatoskr mobile-api && \
  # 11.2 Re-tag the pre-port images as :latest so compose picks them up.
  docker tag ratatoskr:pre-sqlalchemy ratatoskr:latest && \
  docker tag mobile-api:pre-sqlalchemy mobile-api:latest && \
  # 11.3 Restore the SQLite file in place.
  cp data/ratatoskr.db.pre-pg-$(date +%F) data/ratatoskr.db && \
  # 11.4 Restore the env.
  cp .env.pre-pg-$(date +%F) .env && \
  # 11.5 Restart with the legacy stack. Postgres stays in its volume.
  docker compose up -d ratatoskr mobile-api'
```

**Expected:** both containers return to `healthy` within 60 s on the
pre-port images. The bot resumes against SQLite. The Postgres data
remains in `ratatoskr_postgres_data` for a future re-attempt — do
**not** `docker volume rm` it during rollback.

**Recovery time estimate:** **`[VERIFY]`** minutes — to be measured
during the rollback dry-run on the laptop.

---

## Appendix A — Dry-run log

Each row records one dry-run pass. Required before this runbook is
marked ready for production.

| Date | Operator | Snapshot size | ETL dry-run wall-clock | ETL real-run wall-clock | Validation result | Notes |
|---|---|---|---|---|---|---|
| 2026-05-07 | Nikita Pochaev | 521 MB | 1.7 s (35 850 source rows enumerated) | partial — see findings | fail (data-shape bugs) | First pass. Pull via `scp` took 1 min 30 s. |
| 2026-05-07 | Nikita Pochaev | 521 MB | 1.7 s | **12.7 s** | **PASS — zero mismatches** | Pass 2 after Bugs 4–7 were fixed. End-to-end clean on the live Pi snapshot. |
| `[VERIFY]` | `[VERIFY]` | `[VERIFY]` MB | `[VERIFY]` s | `[VERIFY]` s | pass / fail | second-operator dry-run still pending |

### Dry-run pass 1 findings (2026-05-07)

The first dry-run against the live Pi snapshot exposed four
production-data shape issues that the migrator did not handle. Each
was either fixed in the same session or recorded as remaining work.
Production source data is not clean; the migrator must defend
against it.

- **Fixed: FK eager-fetch.** The migrator's `_legacy_row_to_dict`
  used `getattr(row, field_name)` to read each column. For Peewee FK
  fields this triggers an eager related-model lookup, which raises
  `<Parent>DoesNotExist` on dangling FK rows. Switched to
  `getattr(row, col_name)` (e.g. `request_id`) so the raw integer is
  read directly. Source observed: `Summary.request_id=1058` with no
  matching row in `requests`.
- **Fixed: NUL chars in JSONB.** The Pi `summaries.json_payload`
  contains string values with embedded ` `. Postgres `text` /
  `jsonb` rejects them with
  `asyncpg.UntranslatableCharacterError`. Added a
  `_strip_nul_chars` recursive helper that removes `\x00` from all
  string values inside JSON columns during migration. Non-destructive
  in effect (the original SQLite file is preserved for rollback).
- **Fixed: FK orphans (Postgres FK enforcement).** Legacy SQLite
  did not enforce FK constraints (Peewee `ForeignKeyField` is
  metadata-only without `pragmas={"foreign_keys": 1}`). Postgres
  enforces them, so the bulk insert hit
  `ForeignKeyViolationError`. Per the migration plan's risk table,
  added `SET LOCAL session_replication_role = 'replica'` inside each
  bulk-insert transaction, which suspends FK enforcement for the
  duration of the transaction only. Source observed: dangling
  `request_id=1058` again.
- **Fixed: type-confused values (Bug 7).** `LLMCall.cost_usd` (FLOAT
  column) held the string literal `'ok'` for at least one row,
  rejected by asyncpg with `must be real number, not str`. Added a
  `_coerce_scalar` helper that attempts type coercion based on the
  SA column type (`Integer`/`BigInteger`, `Float`/`Numeric`,
  `Boolean`) and nullifies the cell on failure with a WARNING log.
  Other rows in the same batch still migrate; the bad cell becomes
  NULL.

### Dry-run pass 2 result (2026-05-07, after Bugs 4–7 fixed)

```
MIGRATION REPORT
Mode       : LIVE
Source     : tmp/ratatoskr.snapshot.db   (521 MB, from raspi)
Batch size : 500
Elapsed    : 12.7 s
Total source rows : 35 850
Total migrated    : 35 850
Per-table counts  : source == target on EVERY table (zero mismatches)
STATUS: SUCCESS
```

Notable per-table volumes from the live snapshot (used for sizing
the maintenance window):

| Table | Rows | Table | Rows |
|---|---|---|---|
| `audit_logs` | 21 068 | `summary_embeddings` | 1 169 |
| `llm_calls` | 3 689 | `requests` | 1 215 |
| `channel_posts` | 1 341 | `telegram_messages` | 1 189 |
| `channel_post_analyses` | 1 287 | `crawl_results` | 1 164 |
| `summaries` | 1 170 | `user_interactions` | 834 |
| `feed_items` | 1 341 | `digest_delivery` | 136 |

All other tables either zero rows or single-digit counts.

**Wall-clock implication for the Pi**: laptop ran 12.7 s; the Pi is
roughly 3–4× slower for this workload, so budget **45–60 s** for the
ETL itself in section 6, well within the 60-min nominal window.

| Date | Operator | Rollback path | Recovery time | Result |
|---|---|---|---|---|
| `[VERIFY]` | `[VERIFY]` | image-revert + env-revert | `[VERIFY]` min | pass / fail |

## Appendix B — Open verification gates

Acceptance items from
`docs/tasks/issues/migrate-postgres-write-pi-runbook.md` that are not
yet satisfied (must be cleared before C2 starts):

- [ ] Both `ratatoskr:pre-sqlalchemy` / `:post-sqlalchemy` images and
      both `mobile-api:pre-sqlalchemy` / `:post-sqlalchemy` images
      built, pushed, and pulled to the Pi.
- [ ] Two laptop dry-runs of sections 1–10 against a Pi-DB snapshot.
- [ ] One laptop dry-run of section 11 (rollback) — recovery time
      recorded.
- [ ] Maintenance window estimate refined from dry-run timings (replace
      front-matter placeholder).
- [ ] Linked from `docs/SPEC.md` "Deployment and Operations" section.

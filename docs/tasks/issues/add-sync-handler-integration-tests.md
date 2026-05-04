---
title: Add sync handler integration tests covering full/delta/apply + idempotency
status: doing
area: sync
priority: high
owner: Senior Python Backend Engineer
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Add sync handler integration tests covering full/delta/apply + idempotency #repo/ratatoskr #area/sync #status/doing ⏫

## Context

Related: [[add-sync-v2-contract-regression-suite]].

## Objective

Today tests/api/test_sync_service.py only covers SyncService._coerce_iso datetime serialization. The actual handlers (POST /sessions, GET /full, GET /delta, POST /apply in app/api/routers/sync.py) have no integration coverage. tests/test_api_rate_limit_and_sync.py exists but is excluded from CI.

## Expected artifact

- New tests/api/test_sync.py covering:
  - create session returns sessionId in {data,meta} envelope
  - full sync paginated by cursor
  - delta sync after full returns only changed items
  - apply changes with idempotent re-apply (same idempotency key) returns same result without double-applying
  - apply with conflict returns conflict count in envelope without 5xx
- Mark with appropriate pytest marker so they run in CI test job (not skipped like the rate_limit_and_sync file).
- Run via: `pytest tests/api/test_sync.py -v`

## Definition of done

- Tests pass and run on every CI build.
- Tests fail if a sync handler regresses on cursor pagination, idempotency, or conflict surfacing.

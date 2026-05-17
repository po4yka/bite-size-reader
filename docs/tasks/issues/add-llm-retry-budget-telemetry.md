---
title: Persist LLMCall retry-budget columns and surface fallback in summary meta
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Persist LLMCall retry-budget columns and surface fallback in summary meta #repo/ratatoskr #area/observability #status/backlog 🔼

## Goal

Now that the Prometheus signals and the
`RatatoskrLLMRetryExhaustionHigh` alert are in place
(`docs/reference/llm-retry-telemetry.md`), persist the same per-call
data on the `llm_calls` table and propagate it into the summary
`meta` blob so downstream agents and post-hoc analysis can detect
quality drift without scraping Prometheus.

## Scope

- Add nullable columns to `llm_calls`:
  - `fallback_model_used` (`text`) — populated only when the
    successful response came from a model other than the
    request's primary model.
  - `retry_exhausted` (`boolean default false`) — set true on the
    request's final attempt when no model produced a successful
    response.
  - `total_latency_ms` (`integer`) — wall-clock from first attempt
    issued to last attempt returned.
- Alembic migration. Backfill-safe: all columns nullable / default
  false, no historical row rewrites.
- Surface `fallback_model_used` and `retry_exhausted` under
  `meta.routing` in the summary JSON contract (extend
  `docs/SPEC.md` data model section).
- Wire `record_llm_call_retry_exhaustion` (already in
  `app/observability/metrics.py`) at the request-terminal point so
  the counter and the DB row stay consistent.

## Acceptance criteria

- [ ] New columns nullable and migrated via Alembic; downgrade tested.
- [ ] `docs/SPEC.md` data model section documents the columns.
- [ ] Summary `meta.routing` includes `fallback_model_used` and
  `retry_exhausted` when applicable.
- [ ] `tests/test_llm_call_persistence.py` (or similar) exercises
  the three new columns under: primary success, fallback success,
  full exhaustion.

## References

- Prometheus signals + alert: `docs/reference/llm-retry-telemetry.md`
- Recorder functions: `app/observability/metrics.py`
  (`record_llm_call_attempt`, `record_llm_call_retry_exhaustion`,
  `record_llm_call_latency`)
- Existing model: `app/db/models/core.py` (`LLMCall` already has
  `attempt_index` and `attempt_trigger`)

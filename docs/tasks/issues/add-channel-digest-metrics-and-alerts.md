---
title: Add channel digest pipeline metrics and delivery-failure alerts
status: backlog
area: observability
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add channel digest pipeline metrics and delivery-failure alerts #repo/ratatoskr #area/observability #status/backlog ⏫

## Objective

The channel digest subsystem (userbot reader + scheduled
deliveries) has zero Prometheus instrumentation. The userbot
session can silently desync (session expiry, channel removal,
Telethon reconnect storm) and per-user digest failures only
surface in structured logs. Without delivery counters and
userbot-disconnect gauges, broken digests degrade silently.

## Context

- `rg "metric|prometheus|record_" app/adapters/digest/
  app/tasks/digest.py` finds only DB record helpers
  (`async_record_channel_fetch_error` at
  `app/adapters/digest/channel_reader.py:78`); no Prometheus
  instrumentation.
- Failures inside `_run_digest_pipeline`
  (`app/adapters/digest/digest_service.py:166` and `:254`) are
  logged but uncounted.

## Scope

- Counters:
  - `ratatoskr_digest_deliveries_total{status}` (`sent`, `failed`,
    `empty`).
  - `ratatoskr_digest_posts_analyzed_total{status}` (`ok`, `llm_error`,
    `skipped`).
  - `ratatoskr_digest_userbot_reconnects_total`.
  - `ratatoskr_digest_channel_fetch_errors_total{reason}`.
- Histogram: `ratatoskr_digest_pipeline_duration_seconds`.
- Alerts:
  - Digest delivery failure rate > 10% over 1h → warning.
  - Scheduled-digest cron produced zero deliveries despite > 0
    active subscriptions in last 24h → critical.
  - Userbot reconnect rate > 3/h → warning (session-instability
    signal).

## Acceptance criteria

- [ ] All counters and the histogram registered in
  `app/observability/` and incremented in the digest pipeline.
- [ ] Three alert rules in `ops/monitoring/alerting_rules.yml`
  with runbook pointers.
- [ ] Unit test asserts each counter increments on a forced
  scenario (success path, LLM failure, userbot reconnect).

## References

- Pipeline: `app/adapters/digest/digest_service.py:166-260`
- Channel reader: `app/adapters/digest/channel_reader.py:78`
- Task: `app/tasks/digest.py`
- Subsystem doc: `docs/reference/digest-subsystem-ops.md`

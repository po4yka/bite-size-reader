---
title: Wire scraper-chain attempt_log into chain orchestrator and crawl_results
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-17
---

- [ ] #task Wire scraper-chain attempt_log into chain orchestrator and crawl_results #repo/ratatoskr #area/observability #status/backlog 🔼

## Goal

The Prometheus signals
(`ratatoskr_scraper_attempts_total{provider,status}`,
`ratatoskr_scraper_attempt_latency_seconds{provider}`) plus the
`ratatoskr-scraper-chain` Grafana dashboard and the
`ScraperAttemptRecorder` / `serialize_attempt_log` helpers
(`app/adapters/content/scraper/attempt_log.py`) are in place. What
remains is the *wiring* so every real scraper-chain run emits the
counters and persists the attempt log on the `crawl_results` row.

## Scope

- In `app/adapters/content/scraper/` chain orchestrator, instantiate
  one `ScraperAttemptRecorder` per request and call
  `record_scraper_attempt(...)` /
  `record_scraper_attempt_latency(...)` for each provider call.
- Emit a structured `scraper.attempt` log event per attempt (provider,
  correlation_id, url host, latency_ms, status, error class).
- Add a nullable `attempt_log` JSON column to `crawl_results`
  (Alembic migration) and tag the row with the winning provider name
  in an existing column (or add `winning_provider`).
- Persist `serialize_attempt_log(recorder.entries)` into the new
  column at chain end.

## Acceptance criteria

- [ ] Every chain run records one entry per provider call in the
  Prometheus counter + the attempt_log payload.
- [ ] `crawl_results.attempt_log` populated for new runs; downgrade
  migration tested.
- [ ] Structured `scraper.attempt` event includes `correlation_id`
  and is visible in JSON logs.
- [ ] No regression in
  `tests/adapters/content/scraper/` or chain happy-path tests.

## References

- Metrics + recorder helpers: `app/observability/metrics.py`
  (`record_scraper_attempt`, `record_scraper_attempt_latency`)
- Attempt log payload: `app/adapters/content/scraper/attempt_log.py`
- Grafana dashboard: `ops/monitoring/grafana/provisioning/dashboards/ratatoskr-scraper-chain.json`
- Chain code: `app/adapters/content/scraper/`

---
title: Add scraper chain failure correlation and metrics
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-04-30
updated: 2026-05-04
---

- [ ] #task Add scraper chain failure correlation and metrics #repo/ratatoskr #area/observability #status/backlog 🔼

## Goal

Make scraper-chain failures debuggable end-to-end. Motivated by recent provider drift — per-provider telemetry is missing.

## Scope

- Emit a structured `scraper.attempt` event per provider call with: provider name, correlation_id, url host, latency_ms, status (success|error|timeout|skipped), error class.
- Prometheus counters: `scraper_attempts_total{provider,status}`, histogram `scraper_attempt_latency_seconds{provider}`.
- Tag every `crawl_results` row with the winning provider; persist failed-provider list in a new `crawl_results.attempt_log` JSON column (or sibling table).
- Add a Grafana panel under `ops/monitoring/grafana/` showing per-provider success rate + p95 latency.

## Acceptance criteria

- [ ] Logs include `scraper.attempt` for every chain step; correlation_id present.
- [ ] `/metrics` exposes the new counters and histogram.
- [ ] One Grafana JSON dashboard checked into `ops/monitoring/grafana/`.
- [ ] Unit tests cover attempt-log serialization and partial-failure paths.

## References

- `app/adapters/content/scraper/`
- `app/observability/`

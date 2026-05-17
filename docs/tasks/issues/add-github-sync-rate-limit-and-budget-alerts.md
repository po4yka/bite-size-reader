---
title: Add GitHub sync rate-limit outcome label and budget-cap alerts
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add GitHub sync rate-limit outcome label and budget-cap alerts #repo/ratatoskr #area/observability #status/backlog 🔼

## Objective

`app/tasks/github_sync.py:179-188` handles `GitHubRateLimitError` and logs `github_sync_rate_limit`, but `GITHUB_SYNC_RUNS_TOTAL` (`app/observability/metrics_repositories.py:26-56`) has no `ratelimited` outcome label and `ops/monitoring/alerting_rules.yml` has nothing about rate-limit recovery or budget exhaustion. A persistently rate-limited PAT silently halts daily sync for that user, indistinguishable from "no new stars".

## Context

- Rate-limit handling: `app/tasks/github_sync.py:179-193`.
- Counters: `app/observability/metrics_repositories.py:26-56`.
- Existing metrics: `GITHUB_SYNC_RUNS_TOTAL{status}` and `GITHUB_SYNC_LLM_CALLS_TOTAL{trigger}` (`made`, `deferred`).

## Scope

- Add `ratelimited` label value to `GITHUB_SYNC_RUNS_TOTAL{status}` (or new `GITHUB_SYNC_RATE_LIMITED_TOTAL` counter), incremented at `app/tasks/github_sync.py:181`.
- Alerts: - Same user rate-limited > 3 consecutive runs → severity warning (PAT expired or revoked). - `GITHUB_SYNC_LLM_CALLS_TOTAL{trigger="deferred"}` > 90% of `{trigger="made"}` over 24h → severity warning (= budget cap is biting).

## Acceptance criteria

- [ ] New label or counter increments at the rate-limit handler call site.
- [ ] Two alert rules in `ops/monitoring/alerting_rules.yml`.
- [ ] Unit test asserts counter increments on a forced 429.

## References

- Task: `app/tasks/github_sync.py:179-193`
- Metrics: `app/observability/metrics_repositories.py:26-56`
- Related: [[add-github-sync-rate-limit-recovery-test]]

---
title: Add Taskiq retry middleware and dead-letter queue for failed background jobs
status: backlog
area: observability
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add Taskiq retry middleware and dead-letter queue for failed background jobs #repo/ratatoskr #area/observability #status/backlog 🔼

## Objective

`app/tasks/middleware.py:26-54` only tracks chronic failures (3 consecutive); no `RetryMiddleware` is registered. `app/tasks/broker.py:32-53` constructs `RedisStreamBroker` with no `max_retries`/`retry_on_error`. `_result_ttl` defaults to 3600s — failed task payloads vanish after 1h with no operator hook to re-drive a batch. Transient failures (network blips during GitHub sync, OpenRouter timeouts) are not retried; permanent failures leave no inspectable record after the TTL.

## Context

- Middleware: `app/tasks/middleware.py:26-54`.
- Broker: `app/tasks/broker.py:32-53`.
- Grep for `dead_letter` / `DLQ` returns zero hits across `app/tasks/` and `docs/`.

## Scope

- Register `SimpleRetryMiddleware` (taskiq built-in) with per-task `max_retries` labels via task kwargs.
- Persist terminal failures to a `taskiq_failed_jobs` Postgres table (task_name, kwargs, traceback, last_failed_at, attempt_count).
- CLI helper `python -m app.cli.requeue_failed_task <id>` that re-enqueues from the DLQ.
- New Prometheus counter `ratatoskr_taskiq_retries_total{task,outcome}` (`retry`, `dead_letter`, `success_after_retry`).
- Alert when terminal-failure rate > N/15m → severity warning.
- Document operational handling in `docs/runbooks/taskiq-failures.md` (covered by [[add-per-subsystem-runbooks]]).

## Acceptance criteria

- [ ] Transient failures are retried per task policy.
- [ ] Terminal failures persisted to DLQ with full payload.
- [ ] CLI helper re-enqueues a chosen failed job.
- [ ] Metrics + alert wired.

## References

- Middleware: `app/tasks/middleware.py:26-54`
- Broker: `app/tasks/broker.py:32-53`
- Related: [[add-per-subsystem-runbooks]]

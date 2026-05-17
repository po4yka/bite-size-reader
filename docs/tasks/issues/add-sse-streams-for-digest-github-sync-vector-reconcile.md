---
title: Add SSE progress streams for digest runs, GitHub sync, and vector reconcile
status: backlog
area: api
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add SSE progress streams for digest runs, GitHub sync, and vector reconcile #repo/ratatoskr #area/api #status/backlog 🔽

## Objective

Only `GET /v1/requests/{request_id}/stream` exists today. Digest delivery (`app/api/routers/social/digest.py:151` `POST /trigger`), GitHub sync (`app/tasks/github_sync.py`), and vector reconcile (`app/tasks/reconcile_vector_index.py`) all run async with no progress stream. KMP clients can only poll terminal state — no incremental feedback, no cancel.

## User story

As a mobile user triggering a multi-minute starred-repo ingestion or digest assembly, I want to see live progress, so that I know the operation is still going and can cancel if needed.

## Context

- Existing stream: `app/api/routers/content/streams.py:55`.
- StreamHub infrastructure already generic: `app/adapters/content/streaming/`.
- Long-running tasks: `app/tasks/github_sync.py`, `app/tasks/reconcile_vector_index.py`, `app/adapters/digest/digest_service.py`.

## Scope

- New SSE endpoints: - `GET /v1/digest/runs/{run_id}/stream` — events: `phase`, `channel_processed`, `posts_analyzed`, `delivered`, `done`, `error`. - `GET /v1/github/syncs/{sync_id}/stream` — events: `phase`, `repos_fetched`, `repos_analyzed`, `done`, `error`. - `GET /v1/vector-reconciler/runs/{run_id}/stream` — events: `phase`, `rows_scanned`, `rows_requeued`, `done`, `error`.
- Each long-running task publishes to a StreamHub topic keyed by `run_id`.
- Document SSE event schemas in OpenAPI spec.

## Acceptance criteria

- [ ] Each stream delivers progress events to a connected client.
- [ ] Done / error events terminate the stream cleanly.
- [ ] Reconnects pick up at most one event behind.
- [ ] No memory leak if client disconnects mid-stream.

## References

- Existing stream: `app/api/routers/content/streams.py:55`
- StreamHub: `app/adapters/content/streaming/`
- Long-running tasks: `app/tasks/github_sync.py`, `app/tasks/reconcile_vector_index.py`

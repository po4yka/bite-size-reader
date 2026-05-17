---
title: Add DELETE /v1/aggregations/{session_id} endpoint
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Add DELETE /v1/aggregations/{session_id} endpoint #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/api/routers/content/aggregation.py:331, :388` exposes `GET ""` and `GET "/{session_id}"` but no DELETE handler. The OpenAPI spec `docs/openapi/mobile_api.yaml:2015-2068` documents only `GET`. `aggregation_sessions` rows accumulate without any user-controlled delete path; KMP clients have no way to let users dismiss / curate aggregation bundles, leaving stale rollouts and orphaned `aggregation_session_items`.

## User story

As a mobile user who triggered an aggregation, I want to delete the bundle when I'm done with it, so that my history view stays clean and storage doesn't grow forever.

## Context

- Existing handlers: `app/api/routers/content/aggregation.py:331, :388`.
- Service that owns the use case: `app/application/services/multi_source_aggregation_service.py:42-162` — no delete method.
- Spec coverage: `docs/openapi/mobile_api.yaml:2015-2068` (GET only).

## Scope

- New `DELETE /v1/aggregations/{session_id}` (auth required).
- Cascade-delete `aggregation_session_items` for the owning user; returns 204 on success.
- 404 on missing or non-owned session.
- Add delete method to `MultiSourceAggregationService`.
- Update OpenAPI spec mirroring the `delete_repository_v1_repositories_repository_id_delete` envelope shape.

## Acceptance criteria

- [ ] DELETE returns 204 and removes the session + child items.
- [ ] 404 on missing or unowned session.
- [ ] OpenAPI spec entry added.
- [ ] Integration test exercises the endpoint.

## References

- Router: `app/api/routers/content/aggregation.py:331, :388`
- Service: `app/application/services/multi_source_aggregation_service.py:42-162`
- Spec: `docs/openapi/mobile_api.yaml:2015-2068`

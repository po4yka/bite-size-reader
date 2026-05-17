---
title: Fix POST /v1/sync/sessions pagination overstatement (has_more=True with total=0)
status: backlog
area: sync
priority: low
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Fix POST /v1/sync/sessions pagination overstatement (has_more=True with total=0) #repo/ratatoskr #area/sync #status/backlog 🔽

## Objective

`app/api/routers/sync.py:40-46` hard-codes `pagination={"total":0, "has_more":True, ...}` on session creation. A KMP cache layer that keys off `has_more` may re-poll forever after session creation. Semantically meaningless — a session creation response has no rows to paginate. Spec at `docs/openapi/mobile_api.yaml:2535` declares the pagination block, so the bug is in the runtime payload, not the spec.

## Context

- Code: `app/api/routers/sync.py:40-46`.
- Comparator (correct): `app/api/routers/content/summaries.py:213-227`, `app/api/routers/repositories.py:280`, `app/api/routers/collections.py:177` all populate pagination from real counts.
- Spec: `docs/openapi/mobile_api.yaml:2535` declares the block.

## Scope

- Drop the pagination kwarg in `create_sync_session`, OR set `total=1, has_more=False, offset=0, limit=1` to reflect that one session was just created.
- Update or remove the pagination block in the spec for this endpoint if going the "drop" route.
- Snapshot test asserts the response shape.

## Acceptance criteria

- [ ] `POST /v1/sync/sessions` response no longer claims `has_more=True` with `total=0`.
- [ ] Spec and code agree.
- [ ] Existing sync integration tests still pass.

## References

- Code: `app/api/routers/sync.py:40-46`
- Spec: `docs/openapi/mobile_api.yaml:2535`

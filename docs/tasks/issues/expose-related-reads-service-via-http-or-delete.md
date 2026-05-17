---
title: Expose related-reads service via /v1/summaries/{id}/related or delete the dead code
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Expose related-reads service via /v1/summaries/{id}/related or delete the dead code #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/application/services/related_reads_service.py` is fully implemented but has no HTTP consumer anywhere in `app/api/routers/**`. The recommendations endpoint (`/v1/summaries/recommendations`, `app/api/routers/content/summaries.py:244`) delivers a different read model. Either expose related-reads as its own endpoint or delete the dead service — leaving it dual-implemented invites drift.

## Context

- Service: `app/application/services/related_reads_service.py` (entry points exist).
- Aggregation router wires only the full-session POST: `app/api/routers/content/aggregation.py:166`.
- Existing recommendations endpoint (different read model): `app/api/routers/content/summaries.py:244`.

## Scope

Pick ONE direction:

A. **Expose**: add `GET /v1/summaries/{summary_id}/related` driven by `related_reads_service`. Document in OpenAPI spec + reference doc. Integration test asserts a non-empty bundle for a seeded fixture.

B. **Delete**: remove `related_reads_service.py` and any references; record the decision in `docs/decisions/` so a future reader knows why.

## Acceptance criteria

- [ ] Direction chosen and documented in a short decision note under `docs/decisions/`.
- [ ] Code in sync with decision (either endpoint shipped OR dead code removed).
- [ ] If shipped, spec + reference doc + test all updated.

## References

- Service: `app/application/services/related_reads_service.py`
- Existing recommendations: `app/api/routers/content/summaries.py:244`

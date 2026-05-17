---
title: Document /v1/articles/* alias paths in OpenAPI spec
status: backlog
area: api
priority: high
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Document /v1/articles/* alias paths in OpenAPI spec #repo/ratatoskr #area/api #status/backlog ⏫

## Objective

The summaries router is mounted twice in `app/api/main.py` — under `/v1/summaries` and `/v1/articles` — but `docs/openapi/mobile_api.yaml` documents only a partial subset of the alias paths. KMP clients reading the spec will under-generate methods and silently miss half the `/articles/*` namespace.

## Context

- Mount points: `app/api/main.py:251` (summaries) and `app/api/main.py:253` (articles).
- OpenAPI alias coverage in `docs/openapi/mobile_api.yaml:3646-5936` documents: `/v1/articles`, `/v1/articles/{id}`, `/v1/articles/{id}/content`, `/v1/articles/{id}/favorite`, `/v1/articles/by-url`, `/v1/articles/{id}/reading-position`, `/v1/articles/{id}/feedback`, `/v1/articles/{id}/export`, `/v1/articles/recommendations`.
- Missing from spec: - `/v1/articles/bulk/{mark-read,favorite,delete}` (3 endpoints — also tracked by [[document-bulk-summary-endpoints-in-openapi]]). - `/v1/articles/{id}/tags`, `/v1/articles/{id}/tags/{tag_id}` (tags router mounted under `/v1/summaries` at `app/api/main.py:266`).

## Scope

- Either (a) generate the alias paths from a single source of truth during build, or (b) explicitly enumerate every alias path in `docs/openapi/mobile_api.yaml` with `description: "Alias for /v1/summaries/..."` matching the existing convention at `mobile_api.yaml:5802`.
- Add a CI check that `set(code_paths_for(summaries.router)) ⊆ {/v1/summaries/*, /v1/articles/*}` paths in the spec — fail the build on drift.

## Acceptance criteria

- [ ] Every `/v1/summaries/*` endpoint also appears as `/v1/articles/*` in the spec.
- [ ] CI check detects future drift and fails the build.
- [ ] OpenAPI validation passes.

## References

- Router mounts: `app/api/main.py:251-266`
- Summaries router: `app/api/routers/content/summaries.py`
- Spec: `docs/openapi/mobile_api.yaml:3646-5936`
- Related: [[document-bulk-summary-endpoints-in-openapi]]

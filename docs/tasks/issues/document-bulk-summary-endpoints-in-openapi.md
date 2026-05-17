---
title: Document bulk summary endpoints in OpenAPI spec and mobile-api reference
status: backlog
area: api
priority: critical
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Document bulk summary endpoints in OpenAPI spec and mobile-api reference #repo/ratatoskr #area/api #status/backlog 🔺

## Objective

Commit `9a9e5d1b feat(api): bulk favorite + bulk delete endpoints on
summaries` shipped three production-public endpoints that are
absent from `docs/openapi/mobile_api.yaml` and
`docs/reference/mobile-api.md`. This directly contradicts the
"API Surface Freeze Policy" the reference doc enforces and breaks
the contract guarantee the KMP client relies on for typed-client
codegen.

## Context

- Code: `app/api/routers/content/summaries.py:630` (`POST /v1/summaries/bulk/mark-read`),
  `app/api/routers/content/summaries.py:651` (`POST /v1/summaries/bulk/favorite`),
  `app/api/routers/content/summaries.py:673` (`POST /v1/summaries/bulk/delete`).
- Spec: `rg "bulk/mark-read|bulk/favorite|bulk/delete" docs/openapi/mobile_api.yaml`
  returns zero matches; only digest's `bulk-unsubscribe` and
  `bulk-category` are present.
- Reference: no entry under "Summaries and Articles" in
  `docs/reference/mobile-api.md`.
- The summaries router is mounted twice (`app/api/main.py:251` and
  `app/api/main.py:253`), so the same endpoints exist under
  `/v1/articles/bulk/*` as well — also undocumented.

## Scope

- Add three `POST /v1/summaries/bulk/{mark-read,favorite,delete}`
  operations to `docs/openapi/mobile_api.yaml` with request /
  response schemas matching `_BulkMarkReadRequest`,
  `_BulkFavoriteRequest`, `_BulkDeleteRequest`, and the
  `_BulkMarkReadResponse{updated}` envelope.
- Mirror the same operations under `/v1/articles/bulk/*` with
  `description: "Alias for /v1/summaries/bulk/..."` to match the
  existing alias convention (`mobile_api.yaml:5802`).
- Add a "Bulk operations" subsection to
  `docs/reference/mobile-api.md` under "Summaries and Articles".

## Acceptance criteria

- [ ] All three bulk endpoints documented in
  `docs/openapi/mobile_api.yaml` under both `/v1/summaries/bulk/*`
  and `/v1/articles/bulk/*`.
- [ ] Reference doc lists each endpoint with request shape, response
  shape, and authentication requirement.
- [ ] OpenAPI validation (`make openapi-check` or equivalent) passes.

## References

- Code: `app/api/routers/content/summaries.py:630-700`
- Spec: `docs/openapi/mobile_api.yaml`
- Reference: `docs/reference/mobile-api.md` (Summaries and Articles section)
- Related: [[document-articles-alias-paths-in-openapi]]

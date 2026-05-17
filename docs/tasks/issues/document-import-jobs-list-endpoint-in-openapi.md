---
title: Document GET /v1/import list endpoint in OpenAPI spec
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Document GET /v1/import list endpoint in OpenAPI spec #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/api/routers/import_export.py:165` defines `@router.get("/import")` that lists user import jobs, but the OpenAPI spec at `docs/openapi/mobile_api.yaml:5198-5253` documents only `POST /v1/import` and `GET /v1/import/{job_id}`. The operation id `list_import_jobs_v1_import_get` appears under the wrong path block — the LIST GET has no `path` stanza. KMP clients cannot discover historical jobs via the contract; re-opening the app after an import loses the job reference.

## Context

- Code: `app/api/routers/import_export.py:165`.
- Spec: `docs/openapi/mobile_api.yaml:5198-5253` — POST + GET by ID present; LIST missing a path block.
- Related existing entry: `docs/openapi/mobile_api.yaml:5241` (orphan operation id).

## Scope

- Add a `get:` block under `/v1/import:` in `docs/openapi/mobile_api.yaml` describing pagination + envelope.
- Reuse the existing `ImportJob` model shape.
- Confirm `DELETE /v1/import/{job_id}` (present at `import_export.py:174`) is documented at `mobile_api.yaml:5288` — already present, just verify.
- Cross-link in `docs/reference/mobile-api.md` §"Import".

## Acceptance criteria

- [ ] `GET /v1/import` documented with pagination + standard envelope.
- [ ] OpenAPI validation passes.
- [ ] Reference doc updated.

## References

- Code: `app/api/routers/import_export.py:165, :174`
- Spec: `docs/openapi/mobile_api.yaml:5198-5253`

---
title: Derive frontend API module interfaces from generated.ts instead of hand-written types
status: backlog
area: frontend
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-04
updated: 2026-05-04
---

- [ ] #task Derive frontend API module interfaces from generated.ts instead of hand-written types #repo/ratatoskr #area/frontend #status/backlog 🔼

## Objective

`api/generated.ts` is produced by `openapi-typescript` and referenced only for two types in `api/types.ts:13`. The ~20 API modules define their own local interfaces independently. Type drift between backend response shapes and frontend interfaces is caught only at runtime. The CI check confirms `generated.ts` is up to date but nothing enforces that modules *use* it.

## Context

- `clients/web/src/api/generated.ts` — generated from `docs/openapi/mobile_api.yaml`
- `clients/web/src/api/types.ts:13` — partial usage
- `clients/web/src/api/summaries.ts`, `auth.ts`, `collections.ts`, etc. — all define hand-written local interfaces

## Acceptance criteria

- [ ] `SummaryCompact`, `SummaryDetail`, and `Request` types derived from `generated.ts` `components["schemas"]`
- [ ] At least 5 of the 20 API modules updated in the first pass (start with highest-traffic: summaries, requests, auth)
- [ ] CI `web-static-check` job updated to verify that key types are imported from `generated.ts` (lint rule or tsc check)
- [ ] Documented migration plan for remaining modules

## Definition of done

A backend schema change to `SummaryCompact` (e.g. adding a field) causes a `tsc` error in the frontend without manual intervention.

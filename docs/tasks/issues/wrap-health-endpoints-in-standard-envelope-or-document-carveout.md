---
title: Wrap health endpoints in standard envelope or document the carve-out
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Wrap health endpoints in standard envelope or document the carve-out #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/api/routers/health.py` returns raw dicts at the top level —
no `success`/`data`/`meta` wrapper — while the mobile-api
reference doc lists these endpoints under `/v1` without an
envelope carve-out. Lower client impact than other envelope drift
because health is usually polled by infrastructure, but the
API-surface freeze contract is silently violated. If KMP ever
pulls `/v1/health/detailed` for a diagnostics screen, schema
validation will fail.

## Context

- Raw-dict returns:
  - `app/api/routers/health.py:127, 134, 176, 186, 209, 230, 235,
    243, 257`.
- Reference doc: `docs/reference/mobile-api.md:172-181` lists the
  endpoints without an envelope carve-out.

## Scope

Pick ONE direction:

A. Carve out health in `docs/reference/mobile-api.md:87` as raw-dict
   by design and add a note to the OpenAPI spec.

B. Wrap every health endpoint in `success_response(...)` to match
   every other router. If chosen, ensure infrastructure callers
   (Kubernetes liveness probes, uptime monitors) still parse the
   nested `data.status`.

## Acceptance criteria

- [ ] One direction chosen and documented in a short decision note
  under `docs/decisions/`.
- [ ] All health endpoints either wrapped or explicitly carved out.
- [ ] Snapshot test asserts the chosen contract.

## References

- Router: `app/api/routers/health.py:127-257`
- Reference: `docs/reference/mobile-api.md:172-181`
- Envelope spec: `docs/reference/mobile-api.md:87, 102-118`

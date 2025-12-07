# Proposal: Mobile API OpenAPI Typing & Sync Contract Hardening
- Date: 2025-12-07
- Owner: AI Partner
- Status: Draft
- Related Docs: `docs/openapi/mobile_api.yaml`, `.docs/TECH_DESIGNS/TD_response_contracts.md`, `.docs/TECH_DESIGNS/TD_sync_protocol.md`, `docs/MOBILE_API_SPEC.md`

## Context
- Problem / Opportunity: Mobile clients see many `{}`/generic response schemas in the OpenAPI, making generated models weakly typed and error handling inconsistent. Sync endpoints are under-specified for version/conflict semantics.
- Current State: YAML/JSON specs exist but responses for `/v1/*` frequently use empty objects; error codes beyond 422 are undocumented; sync payloads are generic.
- Desired Outcome: Strongly typed, mobile-friendly OpenAPI with explicit envelopes, conflict semantics, and pagination/search metadata to support Kotlin/Swift codegen without `Any`/map fallbacks.

## Goals
- Provide explicit schemas for auth, user/profile/prefs/stats, summaries/search/pagination, requests/status, duplicate checks, and sync (session/full/delta/apply).
- Standardize error responses (401/403/404/409/422/429/500) using a shared envelope with codes and correlation_id.
- Document sync cursor/version/conflict semantics and pagination/query encoding for list/search endpoints.
- Keep `/v1` backward-compatible where possible; version-breaking changes noted.

## Non-Goals
- Backend business logic rewrites or new endpoints.
- DB schema changes beyond fields already assumed in TD_sync_protocol (server_version/deleted_at).

## Options Considered
- Option A: Tighten existing `/v1` spec with explicit schemas and envelopes (chosen for compatibility).
- Option B: Introduce `/v2` with breaking contracts and leave `/v1` as-is (higher effort, less compatible).
- Option C: Generate spec from code-first models only (blocked by current router shapes; slower).

## Decision
- Proceed with Option A: enrich `/v1` OpenAPI with typed schemas and standardized errors while preserving routes/fields; document any edge compatibility notes in META/servers descriptions.

## Impact
- Users / stakeholders: Mobile Android/iOS clients gain concrete models; backend and QA get testable contracts.
- Systems / services: OpenAPI artifacts (YAML/JSON) become the canonical contract; codegen pipelines rely on them.
- Data: No schema migrations; relies on existing version/deleted fields planned in sync design.

## Risks & Mitigations
- Risk: Hidden breaking change if required fields are added. Mitigation: mark nullable fields explicitly, describe defaults, keep prior optional fields optional.
- Risk: Spec/code drift. Mitigation: regenerate JSON from YAML and validate; add doc updates in `.docs` + `docs/`.
- Risk: Codegen gaps (tools missing). Mitigation: run lightweight validation and document any unrun checks as follow-ups.

## Timeline & Milestones
- M1 (Day 0): Update proposal and tech design, audit current OpenAPI gaps.
- M2 (Day 1): Add schemas and error envelopes to YAML; regenerate JSON.
- M3 (Day 1): Validate spec and update `docs/` summaries; record review/ADR if needed.

## Open Questions
- Do we need typed envelopes for future `/v2` or WebSocket push? (out of scope for now)
- Should sync apply accept client notes/annotations beyond read status? (keep as documented in TD_sync_protocol)

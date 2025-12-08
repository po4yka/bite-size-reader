# Response Contract Alignment
- Date: 2025-12-06
- Author: AI Partner

## Context
- Mobile API responses mix raw dicts and partially typed payloads; meta fields are inconsistent (correlation IDs sometimes in headers only, pagination varies, version/build info absent).
- Error handling mixes custom `APIException` envelopes with FastAPI `HTTPException` payloads; meta and codes are not uniform.
- Telegram bot replies and CLI outputs are rich-text or ad-hoc JSON without a documented envelope, making cross-surface observability and client parsing harder.
- Target: align all outward responses (Mobile API, Telegram bot replies, CLI/agents) to typed success/error wrappers with standardized meta (correlation_id, pagination when applicable, API version/build info) and document the contract.

## Goals and Non-Goals
- Goals:
  - Define canonical SuccessResponse/ErrorResponse envelopes with required/optional meta fields.
  - Standardize pagination/meta blocks for list endpoints and ensure correlation_id propagation.
  - Specify surface-specific presentation (API JSON, Telegram/CLI JSON or text) while keeping the same logical contract.
  - Document error code mapping and meta population rules.
- Non-Goals:
  - Change core summarization pipeline logic or database schema beyond fields needed for meta/version.
  - Redesign Telegram copy or UX; only align structure/metadata where feasible.

## Architecture / Flow
- Central envelope helpers build success/error responses and meta blocks:
  - `build_meta(correlation_id, pagination?, version_info?, extra_meta?)`
  - `success_envelope(data, meta)` and `error_envelope(error_detail, meta)`
- FastAPI layer:
  - Exception handlers wrap errors using the envelope and inject correlation_id from `request.state`.
  - Routers return typed payloads via helpers; list endpoints populate pagination.
  - Middleware ensures correlation_id header propagation and version/build injection.
- Telegram/CLI:
  - When emitting structured JSON (attachments or logs), wrap in the same envelope; text replies may reference correlation_id/error_id inline but attach JSON envelope when possible.

## Data Model / Contracts
- SuccessResponse (logical contract):
  - `success: true`
  - `data: object | array | primitive` (endpoint-specific typed payload)
  - `meta: MetaInfo`
- ErrorResponse:
  - `success: false`
  - `error: { code: string, message: string, details?: object, correlation_id?: string, retry_after?: int }`
  - `meta: MetaInfo`
- MetaInfo:
  - `correlation_id: string` (required when available; echoed from header/state)
  - `timestamp: RFC3339 string (UTC, Z)` default now
  - `version: string` (API semantic version)
  - `build: string | null` (e.g., git SHA or image tag; optional)
  - `pagination?: { total: int, limit: int, offset: int, has_more: bool }` for list endpoints
  - `debug?: { latency_ms?: int, backend?: string }` optional, only when debug enabled
- Summary field tiers:
  - `summary_250`: single-sentence hook (<=250 chars).
  - `summary_1000`: compact 3–5 sentence overview; must not reuse TL;DR sentences verbatim.
  - `tldr`: richest 2–3 paragraph narrative that expands on summary_1000 with extra detail/examples/stats; never identical to summary_1000.
- LLM fallback presets for summaries:
  - Primary model attempts (in order): `schema_strict` (structured JSON Schema, base temp/top_p), `schema_relaxed` (same schema with slightly higher temp/top_p), `json_object_guardrail` (json_object with lower temp/top_p to force structure).
  - Fallback models: `json_object_fallback` with the guardrail parameters to maximize valid JSON emission even when structured schema fails.
  - Empty/invalid structured payloads are counted as failed attempts, recorded with model+preset, and advance the retry cursor; `all_llm_attempts_failed` now reports every attempted combination.
  - Optional overrides for preset tuning via env: `OPENROUTER_SUMMARY_TEMPERATURE_RELAXED`, `OPENROUTER_SUMMARY_TOP_P_RELAXED`, `OPENROUTER_SUMMARY_TEMPERATURE_JSON`, `OPENROUTER_SUMMARY_TOP_P_JSON`.
- Prompt guardrails (EN/RU parity):
  - Role: structured summarization agent for Telegram; JSON-only, no Markdown/fences.
  - Explicit field guidance: distinct tiers, evidence-forward key_stats (with source_excerpt), extractive quotes verbatim or empty, no invented names/URLs/numbers, no placeholders like “N/A”.
  - Anti-duplication: avoid sentence reuse across summary_250/summary_1000/TL;DR; dedupe arrays/entities; topic_tags lowercase without punctuation.
  - Output hygiene: valid UTF-8 JSON, no extra keys, keep strings concise within limits.
- Error codes:
  - Use `ErrorCode` enum for API errors; HTTPException paths mapped to standardized codes (e.g., AUTH_ERROR, VALIDATION_ERROR, RATE_LIMIT_EXCEEDED, NOT_FOUND, INTERNAL_ERROR).
- Surface specifics:
  - Mobile API: JSON envelope returned on all routes (including `/` and `/health`), headers keep `X-Correlation-ID`.
  - Telegram: structured JSON attachments use the same envelope; textual replies mention correlation_id/error_id; fallback allowed when Telegram formatting limits apply.
  - CLI/agents: print envelope JSON to stdout for machine readability; human-friendly text may accompany it.
- Telegram Russian translation add-on:
  - When detected content language is non-Russian and the chosen summary language is not Russian, send a second follow-up message with an adapted Russian translation of the final summary (translate the shaped summary JSON, not the raw content).
  - Translation uses OpenRouter chat completion (no schema enforcement), targets concise, fluent Russian with 2–3 short paragraphs plus optional bullet highlights; no change to the JSON contract or storage schema.
  - If translation fails, send a short notice referencing the correlation_id; main summary delivery remains unchanged.

## Decisions
- Adopt Pydantic envelope models/helpers in `app/api/models/responses.py` (and shared helper module for non-API surfaces).
- Extend meta to include `correlation_id`, `version`, optional `build`, optional `pagination`, optional `debug`.
- Require pagination block on list endpoints and trend/search endpoints; omit on non-list responses.
- Standardize error handler output to use `ErrorResponse` across APIException, ValidationError, DB errors, and 500s.
- Telegram formatter attaches envelope JSON for structured outputs; textual messages remain but must include correlation_id on errors.
- CLI outputs adopt the same envelope for JSON prints.

## Risks and Mitigations
- Risk: Backward compatibility for clients expecting bare payloads.
  - Mitigation: Keep `data` shape stable inside envelope; add changelog note and version bump; consider feature flag if needed.
- Risk: Telegram messages may exceed limits with meta blocks.
  - Mitigation: Keep text concise; attach JSON envelope as document; include correlation_id inline only.
- Risk: Missing correlation_id in background tasks.
  - Mitigation: propagate request.state correlation_id into envelope builder; ensure background jobs pass it through.

## Testing Strategy
- Unit: envelope builders (success/error, meta population), error code mapping, pagination helper.
- API integration: sample endpoints (`/v1/summaries`, `/v1/search`, `/v1/requests/*`) assert envelope shape, meta fields, pagination presence, correlation_id echo, version/build values.
- Error paths: 401/403/404/422/429/500 responses use ErrorResponse with codes and correlation_id.
- Telegram/CLI: formatter emits envelope JSON for structured outputs; tests verify correlation_id presence and success/error flags.

## Rollout
- Implement helpers and refactor API handlers first; add Telegram/CLI envelope attachments next.
- Update docs/specs and changelog; bump API version field.
- Monitor logs for envelope validation errors; add temporary feature toggle if needed.

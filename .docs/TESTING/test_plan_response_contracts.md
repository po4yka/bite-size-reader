# Response Contract Test Plan
- Date: 2025-12-06
- Author: AI Partner

## Scope
- Success/error envelope alignment across surfaces:
  - Mobile API endpoints: auth, summaries, requests, search, sync, user.
  - Global exception handlers and middleware (correlation_id propagation, version/build meta).
  - Telegram structured JSON attachments and error notifications.
  - CLI/agent structured outputs.

## Test Types
- Unit:
  - Meta builder: correlation_id passthrough, timestamp format, version/build defaults, pagination serialization.
  - Success/error envelope helpers: shape, default meta, BaseModel dumping.
  - Error code mapping for APIException/ValidationError/DB errors.
- Integration:
  - FastAPI endpoints return envelopes with meta/pagination where applicable.
  - Headers echo `X-Correlation-ID`; body meta.correlation_id matches.
  - Rate-limit/validation/auth failures return ErrorResponse with codes and correlation_id.
  - Version/build fields set from config.
- E2E:
  - Telegram: reply_json attachment contains envelope with success/error flags and correlation_id; error notifications include correlation_id text.
  - CLI: stdout JSON for summary command wrapped in SuccessResponse; errors wrap in ErrorResponse.

## Environments / Data
- Config: set `X-Correlation-ID` header in requests; provide version/build via config or env.
- Redis optional; when absent, expect rate-limit errors to still use ErrorResponse.
- Test data: seeded user, summaries, requests; mock Telegram client for formatter tests; mock CLI inputs.

## Test Cases
- TC1: GET `/v1/summaries` returns SuccessResponse with pagination meta, correlation_id, version/build; `success` true and data.summaries list typed.
- TC2: POST `/v1/requests` duplicate path returns SuccessResponse with `is_duplicate=true`, meta present.
- TC3: GET `/v1/search` 400/500 path uses ErrorResponse with code/message/correlation_id; pagination omitted.
- TC4: Rate limit exceeded returns 429 with ErrorResponse and retry_after; meta includes correlation_id/version.
- TC5: Validation error (422) returns ErrorResponse code VALIDATION_ERROR, details.fields present.
- TC6: Telegram formatter `reply_json` attaches SuccessResponse envelope; `send_error_notification` embeds correlation_id in JSON and text.
- TC7: CLI summary command success prints SuccessResponse envelope; failure prints ErrorResponse.
- TC8: Summary shaping enriches TL;DR when the model returns TL;DR identical to summary_1000 (adds key ideas/highlights/stats so TL;DR is longer and not verbatim).
- TC9: Summary shaping enriches TL;DR when TL;DR is highly similar (not identical) to summary_1000.
- TC10: Prompt text (EN/RU) instructs: JSON-only (no Markdown/fences), distinct tiers (hook vs 3–5 sentence overview vs 2–3 paragraph TL;DR), no invented data/URLs/names, extractive quotes verbatim or empty, topic_tags lowercase without punctuation.
- TC11: For non-Russian detected content when chosen summary language is not Russian, Telegram sends the original structured summary plus a second follow-up message with an adapted Russian translation; on translation failure, a notice is sent while the main summary still delivers.
- TC12: HTTP 200 responses with missing required summary fields trigger preset retries (`schema_strict` → `schema_relaxed` → `json_object_guardrail` → `json_object_fallback`), and `models_tried`/`total_attempts` reflect every attempted preset+model.
- TC13: Fallback models use `json_object_fallback` parameters (lower temperature/top_p) and succeed after primary structured attempts returned empty payloads.

## Non-Functional
- Load: envelope helpers are allocation-light; pagination meta computed without N+1 queries.
- Security: no secrets in meta; correlation_id redaction not required; error messages avoid stack traces in non-debug mode.
- Resiliency: missing correlation_id falls back to generated value; Redis outages still return envelopes.

## Exit Criteria
- All unit/integration tests above pass.
- API contract snapshots reviewed against design.
- Telegram/CLI outputs verified for envelope + correlation_id.

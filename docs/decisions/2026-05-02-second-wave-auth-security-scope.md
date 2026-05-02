# Second-Wave Auth/Security Policy Scope

Status: decided
Date: 2026-05-02

## Context

Ratatoskr now has multiple authenticated client classes:

- mobile and web clients using bearer JWTs issued by `/v1/auth/telegram-login` and refreshed through `/v1/auth/refresh`
- Telegram WebApp contexts using `X-Telegram-Init-Data`
- CLI, automation, and hosted MCP clients using the client-secret exchange at `/v1/auth/secret-login`

The current contract is documented in `docs/MOBILE_API_SPEC.md` and implemented across `app/api/routers/auth/`.
The Kotlin Multiplatform client already depends on bearer refresh behavior in
`ratatoskr-client/core/data/src/commonMain/kotlin/com/po4yka/ratatoskr/data/remote/ApiClient.kt`,
so backend auth policy changes can affect mobile wire behavior and stored-session semantics.

## Decision

Second-wave auth/security work is approved only for policy hardening and contract
stabilization. It must not introduce a new auth mechanism, replace JWT refresh,
or change the successful response envelope without a separate cross-repo API
decision.

Approved scope:

1. Make auth mode policy explicit in backend docs and OpenAPI:
   - JWT bearer is the default for mobile, browser JWT, CLI, automation, and MCP API access.
   - Telegram WebApp initData remains a separate strict path for WebApp-only contexts.
   - Client-secret login remains limited to CLI, MCP, and automation-style client IDs.
2. Harden deployment defaults without breaking local development:
   - production/staging must configure `JWT_SECRET_KEY`
   - production/staging must configure `ALLOWED_CLIENT_IDS`
   - production/staging must configure `ALLOWED_USER_IDS` unless the deployment is explicitly declared multi-user
3. Add rate-limit policy coverage for auth endpoints:
   - login and secret-login endpoints need stricter per-user/per-client/per-IP limits
   - refresh endpoint needs abuse protection that does not lock out normal token rotation
4. Add audit/logging policy coverage:
   - continue redacting authorization and token-bearing values
   - record auth success/failure events with correlation IDs and safe client/user identifiers
   - never log plaintext client secrets, refresh tokens, access tokens, Telegram initData, or auth hashes
5. Clarify refresh-token/session semantics:
   - refresh remains rotating
   - detected refresh-token reuse revokes the user's active refresh tokens
   - session listing/revocation remains stable for the mobile client
6. Add verification coverage:
   - backend tests for configured/unconfigured allowlists, client-ID validation, secret-login eligibility, refresh reuse behavior, and sensitive log redaction
   - mobile client tests only if the backend wire shape or error handling contract is touched

Out of scope for this wave:

- OAuth/social login productionization beyond documenting any already-present experimental endpoints
- passkeys/WebAuthn
- SSO
- new account model or multi-tenant role model
- changing access-token or refresh-token field names
- changing mobile stored-token format
- broad CORS/CSP/web hardening unrelated to auth endpoints unless a concrete auth issue requires it

## Execution Plan

Create implementation child issues in this order:

1. Backend policy documentation and OpenAPI alignment.
2. Backend auth hardening tests and small implementation fixes discovered by those tests.
3. Backend auth rate-limit/audit policy implementation.
4. KMP client compatibility review against the final OpenAPI/auth behavior.

The KMP review is blocked until the backend implementation issue publishes the
final contract diff. No RIPDPI work is implicated.

## Acceptance Criteria

- `docs/MOBILE_API_SPEC.md`, `docs/SPEC.md`, and `docs/openapi/mobile_api.yaml` agree on auth modes, client types, token rotation, and allowlist behavior.
- Backend tests prove policy behavior for allowlists, client IDs, secret-login eligibility, refresh rotation/reuse, and log redaction.
- Any mobile-visible change is reflected in ratatoskr-client DTO/API tests before release.
- Existing successful auth response envelope remains backward-compatible for the mobile client.

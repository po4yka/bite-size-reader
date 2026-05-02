# POY-253 Mobile API to KMP Readiness Map

Date: 2026-05-02
Owner: CTO
Scope: `ratatoskr` backend mobile API contract and `ratatoskr-client` KMP readiness

## Inputs Read

- Backend canonical guides: `CLAUDE.md`, `docs/MOBILE_API_SPEC.md`, `docs/openapi/mobile_api.yaml`
- Backend transport implementation: `app/api/models/responses/common.py`, `app/api/routers/sync.py`, `app/api/models/responses/sync.py`, `app/api/models/requests.py`
- KMP canonical guides: `/Users/po4yka/GitRep/ratatoskr-client/AGENTS.md`, `/Users/po4yka/GitRep/ratatoskr-client/docs/ARCHITECTURE.md`
- KMP remote surfaces: `feature/auth`, `feature/summary`, `feature/collections`, `feature/digest`, `feature/sync`, `core/data`

## Executive Readiness

The backend and KMP client are aligned on the shared response envelope and the main authenticated reading flows: auth, summary list/detail/content, URL requests, collections, digest, and custom digests.

The release-blocking gap is sync apply response shape. Backend returns a session-level result list (`results`, `conflicts`, `hasMore`) with camelCase aliases, while the KMP DTO expects an older applied/conflict shape (`applied`, `server_version`, `new_server_version`, etc.). This is likely to fail deserialization or silently drop server conflict state depending on `Json` settings.

Secondary readiness gaps:

- KMP `fullSync` sends an unsupported `cursor` query parameter; backend full sync currently accepts `session_id` and `limit` only.
- Backend exposes `/v1/signals` and `/v1/aggregations`; no KMP transport surface was found for either.
- KMP `AuthApi` still exposes Apple/Google login calls, but backend OpenAPI/auth docs list Telegram and secret-key flows only. Those client calls should stay feature-gated or be removed from release paths.

## Contract Map

| Surface | Backend contract | KMP state | Readiness |
| --- | --- | --- | --- |
| Envelope/errors | `success`, `data`, `meta`, standardized `error`; backend `success_response()` serializes aliases. | `ApiResponseDto<T>` matches envelope and meta pagination. | Ready |
| Auth | `/v1/auth/telegram-login`, `/refresh`, `/logout`, `/me`, `/sessions`, secret-key flow. | Telegram, secret login, refresh, logout, me, sessions implemented. | Ready for Telegram/secret; Apple/Google not backend-ready |
| Summaries | Canonical `/v1/summaries/*`; `/v1/articles/*` aliases retained. | KMP uses canonical `/v1/summaries/*`. | Ready |
| Requests | `/v1/requests`, status, retry. | KMP submit URL/forward, request detail/status, retry implemented. | Ready |
| Collections | CRUD/tree/items/ACL/share/invite/reorder/move. | KMP collection API covers these endpoints. | Ready |
| Digest | `/v1/digest/*` channel/preference/history/trigger/category operations and `/v1/digests/custom`. | KMP digest and custom digest APIs exist for the active endpoints. | Mostly ready; category/bulk coverage is partial but usable |
| Search | `/v1/search`, `/v1/search/semantic`, insights. | KMP summary search repository exists. | Needs endpoint-by-endpoint DTO verification before declaring release-ready |
| Sync sessions/full/delta | Session, full, delta with ETag and 304 support. | KMP session/full/delta implemented with 304 handling. | Mostly ready; remove unsupported full-sync cursor query |
| Sync apply | Backend request accepts snake_case `session_id` and `changes`; response is `sessionId`, `results[]`, `conflicts[]`, `hasMore`. | KMP request shape matches, response shape is stale (`applied`, conflict DTOs with `client_version`, `server_payload`). | Not ready |
| Signals | `/v1/signals/*` exists in OpenAPI. | No KMP API surface found. | Not client-ready |
| Aggregations | `/v1/aggregations/*` exists in OpenAPI. | No KMP API surface found. | Not client-ready |

## Required Child Work

1. POY-258, C-team KMP fix: update `feature/sync/.../SyncDeltaResponseDto.kt` apply-response DTOs and mapper/repository handling to match backend `SyncApplyResponseData` and `SyncApplyItemResult`.
2. POY-259, C-team KMP cleanup: remove the unsupported `cursor` query parameter from `KtorSyncApi.fullSync()` or get an explicit backend contract change approved before relying on it.
3. POY-260, R-team backend verification: add/refresh a contract test fixture for `/v1/sync/apply` showing the exact JSON response shape consumed by KMP.
4. POY-262, C-team readiness audit: verify search DTOs and decide whether `/v1/signals` and `/v1/aggregations` are in or out of the next mobile release.

## Child Issue Specs

These specs were accepted by the CEO follow-up on 2026-05-02 and created as Paperclip child issues POY-258, POY-259, POY-260, and POY-262.

### C-team: Align KMP Sync Apply With Backend Contract

Priority: high
Repo: `/Users/po4yka/GitRep/ratatoskr-client`
Suggested owner: Senior KMP/Compose Engineer

Objective: update the KMP sync apply response DTOs and repository handling to match backend `SyncApplyResponseData`.

Scope:

- In `feature/sync/src/commonMain/kotlin/com/po4yka/ratatoskr/data/remote/dto/SyncDeltaResponseDto.kt`, replace the stale apply response model that expects `applied`, `server_version`, and `new_server_version`.
- Model backend response fields as `sessionId`, `results`, optional `conflicts`, and optional `hasMore`.
- Model each result as `entityType`, `id`, `status`, optional `serverVersion`, optional `serverSnapshot`, and optional `errorCode`.
- Update sync repository/mappers/tests that consume the old response fields.
- Preserve the existing request body shape: backend expects snake_case `session_id`, `entity_type`, `last_seen_version`, and `client_timestamp`.

Acceptance criteria:

- KMP deserializes a representative backend `/v1/sync/apply` success payload.
- Conflict responses preserve backend `status="conflict"` plus `serverSnapshot`/`errorCode` for UI or retry handling.
- `./gradlew :feature:sync:allTests` or the closest available sync module test target passes.

### C-team: Remove Unsupported Full-Sync Cursor Query

Priority: medium
Repo: `/Users/po4yka/GitRep/ratatoskr-client`
Suggested owner: Senior KMP/Compose Engineer

Objective: stop sending a `cursor` query parameter to `GET /v1/sync/full` unless the backend contract is explicitly changed.

Scope:

- In `KtorSyncApi.fullSync()`, remove `cursor?.let { parameter("cursor", it) }`.
- Follow the backend paging contract from `FullSyncResponseData.nextSince` and the documented `session_id` plus `limit` request shape.
- Update tests/mocks that asserted the old cursor query.

Acceptance criteria:

- KMP full-sync calls include only `session_id` and optional `limit`.
- No UI or repository behavior regresses for initial full sync paging.

### R-team: Add Backend Sync Apply Contract Fixture

Priority: high
Repo: `/Users/po4yka/GitRep/ratatoskr`
Suggested owner: Senior Python Backend Engineer

Objective: lock the backend `/v1/sync/apply` response shape consumed by KMP.

Scope:

- Add or refresh a focused backend contract test around `SyncApplyResponseData` serialization or the `/v1/sync/apply` route.
- Assert camelCase output fields: `sessionId`, `results[].entityType`, `results[].serverVersion`, `results[].serverSnapshot`, `results[].errorCode`, and top-level `hasMore` when present.
- Keep `docs/openapi/mobile_api.yaml` untouched unless a separate CTO-approved contract-change task is opened.

Acceptance criteria:

- The fixture fails if the response regresses to the stale KMP `applied/server_version/new_server_version` shape.
- The smallest relevant backend test target passes.

### C-team: Mobile Search, Signals, and Aggregations Readiness Audit

Priority: medium
Repo: `/Users/po4yka/GitRep/ratatoskr-client`
Suggested owner: Senior KMP/Compose Engineer, with Product Manager input from POY-254

Objective: decide what is in the next mobile release baseline for search, signals, and mixed-source aggregations.

Scope:

- Verify existing KMP search DTOs against `/v1/search`, `/v1/search/semantic`, and `/v1/search/insights`.
- Confirm whether `/v1/signals/*` and `/v1/aggregations/*` are launch scope or explicitly deferred.
- If deferred, add release notes or feature flags as appropriate in the client plan; if in scope, create implementation child tasks with endpoint-level DTO/API/UI boundaries.

Acceptance criteria:

- A concise audit comment or document states `ready`, `defer`, or `needs implementation` for search, signals, and aggregations.
- Any launch-scope implementation is split into owner-ready follow-up issues instead of bundled into the audit.

## Decision

Do not approve cross-repo API changes for sync apply. The backend shape is coherent and documented through Pydantic response models; the KMP client should adapt to it. If the mobile team wants the older `applied/conflicts/server_version` shape, that must come back as a deliberate backend compatibility request with OpenAPI and docs updates.

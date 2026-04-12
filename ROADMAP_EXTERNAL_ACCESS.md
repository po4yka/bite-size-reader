# External Access Roadmap: CLI and MCP for Multi-Source Aggregation

## Goal

Provide external users with access to multi-source aggregation through:

- a first-class CLI
- an MCP surface for AI agents

The implementation should reuse the existing aggregation workflow and REST API, preserve per-user isolation, and avoid exposing the current single-user MCP runtime model directly to the public internet.

## Scope

This roadmap covers:

- public API hardening for aggregation
- external-user authentication and client provisioning
- CLI support for bundle submission and retrieval
- MCP support for aggregation tools and resources
- multi-user MCP architecture
- deployment, security, observability, and rollout

This roadmap does not cover:

- new extractor work for unsupported platforms
- non-URL public submissions as an MVP
- replacing the existing Telegram product surface

## Current State

### Already Available

- `POST /v1/aggregations` and `GET /v1/aggregations/{session_id}` exist for authenticated API users.
- Aggregation rollout gates already exist.
- The CLI already supports JWT-backed login and authenticated REST calls.
- The MCP server already supports read-only article and search tools.

### Missing

- CLI commands for aggregation bundles.
- MCP tools/resources for aggregation.
- A public multi-user MCP auth model.
- A public provisioning story for external CLI/MCP users.
- A list/browse surface for aggregation sessions.
- Async/session-progress semantics suitable for long-running external requests.
- Production guardrails for public aggregation traffic.

## Guiding Decisions

### Decision 1: REST API is the write source of truth

All write operations for external aggregation should go through the aggregation API or the same application service contract behind it. Do not create CLI-only or MCP-only execution paths with separate business logic.

### Decision 2: Public MVP is URL-first

The public contract should start with URL submissions only. That already covers:

- X post/article links
- Threads links
- Instagram post/carousel/reel links
- article links
- Telegram post links
- YouTube links

Raw Telegram message payloads, file uploads, and binary media ingestion should be treated as a separate phase after the public URL flow is stable.

### Decision 3: CLI is a thin authenticated API client

The CLI should remain a small wrapper over the public API. It should not embed extraction logic or bypass server-side rollout, auth, validation, or persistence.

### Decision 4: Public MCP must be request-scoped and authenticated

The current MCP server model is process-scoped via `MCP_USER_ID` and is suitable for local/single-user use. It is not sufficient for public multi-user exposure. Public MCP access must resolve user identity per request.

### Decision 5: Ship CLI before public MCP

CLI is lower risk because it already fits the existing auth model and REST API shape. MCP should follow after the API and public auth model are stable.

## Target UX

### CLI UX

```bash
bsr aggregate https://x.com/... https://youtube.com/watch?v=...
bsr aggregate --file sources.txt
bsr aggregate --lang en --hint x_post https://x.com/... --hint youtube_video https://youtu.be/...
bsr aggregation get 42
bsr aggregation list --limit 20
```

### MCP UX

Proposed tools:

- `create_aggregation_bundle(items, lang_preference="auto", metadata=None)`
- `get_aggregation_bundle(session_id)`
- `list_aggregation_bundles(limit=20, offset=0)`
- `check_source_supported(url)`

Proposed resources:

- `bsr://aggregations/recent`
- `bsr://aggregations/{id}`
- `bsr://aggregations/stats`

## Phase 1: Public API Contract Hardening

### Objective

Make the aggregation API stable and explicitly suitable for external clients.

### TODO

- [ ] Freeze the public `CreateAggregationBundleRequest` contract for URL-first submissions.
- [ ] Define and document allowed `source_kind_hint` values.
- [ ] Validate max item count, per-item URL length, metadata size, and duplicate handling rules.
- [ ] Decide whether `POST /v1/aggregations` remains synchronous or becomes create-and-return-session immediately.
- [ ] Add `GET /v1/aggregations` to list a user’s aggregation sessions.
- [ ] Decide whether `DELETE /v1/aggregations/{id}` or cancel support is required.
- [ ] Ensure all aggregation endpoints are consistently scoped by authenticated user.
- [ ] Standardize response envelopes for `pending`, `processing`, `completed`, `partial`, and `failed`.
- [ ] Add explicit progress fields to the aggregation session response.
- [ ] Add public error codes for unsupported sources, rollout denial, auth denial, validation failure, quota exhaustion, and upstream extraction failure.

### Files

- [app/api/routers/aggregation.py](/Users/po4yka/GitRep/bite-size-reader/app/api/routers/aggregation.py)
- [app/api/models/requests.py](/Users/po4yka/GitRep/bite-size-reader/app/api/models/requests.py)
- [app/application/services/multi_source_aggregation_service.py](/Users/po4yka/GitRep/bite-size-reader/app/application/services/multi_source_aggregation_service.py)
- [docs/SPEC.md](/Users/po4yka/GitRep/bite-size-reader/docs/SPEC.md)
- [docs/reference/api-contracts.md](/Users/po4yka/GitRep/bite-size-reader/docs/reference/api-contracts.md)
- [docs/reference/api-error-codes.md](/Users/po4yka/GitRep/bite-size-reader/docs/reference/api-error-codes.md)

### Deliverables

- Stable external aggregation API contract.
- User-scoped create/get/list session APIs.
- Clear status and error semantics for external clients.

## Phase 2: Auth and External User Provisioning

### Objective

Make external access operationally usable, not just technically possible.

### TODO

- [ ] Decide the initial access model: admin-issued secrets only, invite-only onboarding, or self-serve account provisioning.
- [ ] Review `ALLOWED_USER_IDS` and fail-open/fail-closed behavior for API JWT auth.
- [ ] Define the supported client types for external use: `cli`, `mcp`, `web`, `automation`, or similar.
- [ ] Add documented client ID naming rules and secret rotation rules.
- [ ] Add owner/admin workflows to issue, rotate, and revoke client secrets for external users.
- [ ] Decide whether non-owner users can self-create secondary client secrets after initial onboarding.
- [ ] Add auth rate limiting and lockout monitoring for `secret-login`.
- [ ] Document onboarding for external users from first login to first aggregation request.
- [ ] Ensure JWT refresh and revoke semantics are documented for long-lived CLI/MCP clients.

### Files

- [app/api/routers/auth/dependencies.py](/Users/po4yka/GitRep/bite-size-reader/app/api/routers/auth/dependencies.py)
- [app/api/routers/auth/endpoints_secret_keys.py](/Users/po4yka/GitRep/bite-size-reader/app/api/routers/auth/endpoints_secret_keys.py)
- [clients/cli/src/bsr_cli/auth.py](/Users/po4yka/GitRep/bite-size-reader/clients/cli/src/bsr_cli/auth.py)
- [docs/tutorials/quickstart.md](/Users/po4yka/GitRep/bite-size-reader/docs/tutorials/quickstart.md)
- [docs/environment_variables.md](/Users/po4yka/GitRep/bite-size-reader/docs/environment_variables.md)

### Deliverables

- A supported onboarding path for external CLI/MCP users.
- Clear auth and client provisioning rules.

## Phase 3: CLI Aggregation MVP

### Objective

Expose aggregation bundles through the existing authenticated CLI.

### TODO

- [ ] Add `BSRClient.create_aggregation_bundle(...)`.
- [ ] Add `BSRClient.get_aggregation_bundle(session_id)`.
- [ ] Add `BSRClient.list_aggregation_bundles(...)` once the API supports it.
- [ ] Add a top-level `bsr aggregate` command for bundle submission.
- [ ] Support positional URL arguments.
- [ ] Support `--file sources.txt` input.
- [ ] Support `--lang auto|en|ru`.
- [ ] Support repeatable `--hint <source_kind>` values with a predictable mapping to submitted items.
- [ ] Add human-readable output for session status, source counts, failures, and final aggregation summary.
- [ ] Add JSON output parity for scripting.
- [ ] Add help text and examples for all new commands.
- [ ] Decide whether the CLI should poll until completion by default or return immediately with a session ID.

### Files

- [clients/cli/src/bsr_cli/client.py](/Users/po4yka/GitRep/bite-size-reader/clients/cli/src/bsr_cli/client.py)
- [clients/cli/src/bsr_cli/main.py](/Users/po4yka/GitRep/bite-size-reader/clients/cli/src/bsr_cli/main.py)
- [clients/cli/src/bsr_cli/output.py](/Users/po4yka/GitRep/bite-size-reader/clients/cli/src/bsr_cli/output.py)
- [clients/cli/README.md](/Users/po4yka/GitRep/bite-size-reader/clients/cli/README.md)
- [docs/reference/cli-commands.md](/Users/po4yka/GitRep/bite-size-reader/docs/reference/cli-commands.md)

### Deliverables

- A working CLI submission flow for mixed-source URL bundles.
- Scripting-friendly JSON output.

## Phase 4: Session Lifecycle and Long-Running Job Semantics

### Objective

Make aggregation safe and usable for long-running public workloads.

### TODO

- [ ] Decide the canonical execution model: blocking request, background job, or hybrid.
- [ ] If needed, split create from execution completion so `POST /v1/aggregations` returns quickly with session metadata.
- [ ] Persist per-item progress and bundle-level progress percentages.
- [ ] Add `queued_at`, `started_at`, `completed_at`, and `last_progress_at` fields if missing.
- [ ] Add polling guidance for CLI and MCP clients.
- [ ] Add timeout semantics and clear failure codes when upstream extraction or synthesis exceeds limits.
- [ ] Add idempotency guidance for retrying the same bundle request.
- [ ] Decide whether duplicate bundles should be de-duplicated or always re-run.

### Files

- [app/application/services/multi_source_aggregation_service.py](/Users/po4yka/GitRep/bite-size-reader/app/application/services/multi_source_aggregation_service.py)
- [docs/reference/data-model.md](/Users/po4yka/GitRep/bite-size-reader/docs/reference/data-model.md)
- [docs/SPEC.md](/Users/po4yka/GitRep/bite-size-reader/docs/SPEC.md)

### Deliverables

- Stable session lifecycle for long-running external aggregation jobs.
- Predictable polling and retry behavior.

## Phase 5: Local MCP Write Support

### Objective

Add aggregation support to MCP for local and trusted single-user use first.

### TODO

- [ ] Add `create_aggregation_bundle` MCP tool.
- [ ] Add `get_aggregation_bundle` MCP tool.
- [ ] Add `list_aggregation_bundles` MCP tool after list API support exists.
- [ ] Add `check_source_supported` MCP tool if useful for agents.
- [ ] Add `bsr://aggregations/recent` resource.
- [ ] Add `bsr://aggregations/{id}` resource if the framework supports parameterized resources cleanly.
- [ ] Keep these tools disabled or undocumented for unauthenticated public SSE until Phase 6 is complete.
- [ ] Decide whether local MCP tools should call application services directly or call the HTTP API.

### Files

- [app/mcp/tool_registrations.py](/Users/po4yka/GitRep/bite-size-reader/app/mcp/tool_registrations.py)
- [app/mcp/resource_registrations.py](/Users/po4yka/GitRep/bite-size-reader/app/mcp/resource_registrations.py)
- [app/mcp/server.py](/Users/po4yka/GitRep/bite-size-reader/app/mcp/server.py)
- [docs/mcp_server.md](/Users/po4yka/GitRep/bite-size-reader/docs/mcp_server.md)

### Deliverables

- Aggregation-aware MCP tools for local/trusted agent use.

## Phase 6: Public Multi-User MCP Architecture

### Objective

Replace the current process-scoped MCP user model with a request-scoped public architecture.

### TODO

- [ ] Decide whether to evolve the existing MCP server or add a separate public MCP gateway.
- [ ] Introduce request-scoped authentication for MCP requests using the same user identity model as the API.
- [ ] Remove dependence on static startup scoping for public MCP requests.
- [ ] Ensure every MCP tool call resolves the effective user ID from the authenticated request, not from process config.
- [ ] Decide whether bearer tokens are passed directly to MCP or terminated by a trusted gateway.
- [ ] Add secure token forwarding from the MCP transport layer to request context.
- [ ] Keep the existing `MCP_USER_ID` model for local stdio/SSE where it still adds value.
- [ ] Document the difference between local MCP mode and public hosted MCP mode.
- [ ] Validate that read tools and write tools are both user-scoped under the new model.

### Files

- [app/mcp/context.py](/Users/po4yka/GitRep/bite-size-reader/app/mcp/context.py)
- [app/mcp/server.py](/Users/po4yka/GitRep/bite-size-reader/app/mcp/server.py)
- [app/cli/mcp_server.py](/Users/po4yka/GitRep/bite-size-reader/app/cli/mcp_server.py)
- [docs/mcp_server.md](/Users/po4yka/GitRep/bite-size-reader/docs/mcp_server.md)

### Deliverables

- A real multi-user public MCP deployment model.
- No process-wide user leakage risk for hosted MCP.

## Phase 7: Security, Abuse Controls, and Cost Guardrails

### Objective

Protect the system before widening external access.

### TODO

- [ ] Add per-user and per-client rate limits for aggregation creation.
- [ ] Add bundle size, metadata size, and concurrent-job limits.
- [ ] Add per-user cost ceilings or quotas for multimodal/video-heavy runs.
- [ ] Review SSRF and blocked-address protections for all public URL ingestion paths.
- [ ] Ensure secrets, bearer tokens, and upstream auth headers are redacted from logs.
- [ ] Add request auditing for who created each aggregation session and from which client ID.
- [ ] Add anomaly detection for repeated failed logins, repeated extractor failures, and quota abuse.
- [ ] Define retention rules for extracted media/transcripts that come from public external requests.
- [ ] Review terms/compliance implications for externally submitted social-platform URLs.

### Files

- [app/api/routers/proxy.py](/Users/po4yka/GitRep/bite-size-reader/app/api/routers/proxy.py)
- [app/api/routers/auth/endpoints_secret_keys.py](/Users/po4yka/GitRep/bite-size-reader/app/api/routers/auth/endpoints_secret_keys.py)
- [docs/explanation/observability-strategy.md](/Users/po4yka/GitRep/bite-size-reader/docs/explanation/observability-strategy.md)
- [docs/DEPLOYMENT.md](/Users/po4yka/GitRep/bite-size-reader/docs/DEPLOYMENT.md)

### Deliverables

- Public aggregation with explicit rate, quota, and audit controls.

## Phase 8: Documentation and Integration Guides

### Objective

Make the external surfaces self-serve for users and integrators.

### TODO

- [ ] Document the public aggregation API with example create/get/list requests.
- [ ] Add CLI docs for `bsr aggregate` and `bsr aggregation`.
- [ ] Add MCP docs for local use and hosted public use.
- [ ] Add onboarding docs for external users receiving their first client secret.
- [ ] Add sample workflows for:
  - [ ] human CLI use
  - [ ] shell scripting with `--json`
  - [ ] local agent integration over stdio
  - [ ] hosted MCP client integration
- [ ] Add troubleshooting docs for rollout denial, auth failures, unsupported source URLs, and timed-out jobs.

### Files

- [clients/cli/README.md](/Users/po4yka/GitRep/bite-size-reader/clients/cli/README.md)
- [docs/mcp_server.md](/Users/po4yka/GitRep/bite-size-reader/docs/mcp_server.md)
- [docs/tutorials/quickstart.md](/Users/po4yka/GitRep/bite-size-reader/docs/tutorials/quickstart.md)
- [docs/TROUBLESHOOTING.md](/Users/po4yka/GitRep/bite-size-reader/docs/TROUBLESHOOTING.md)
- [docs/reference/cli-commands.md](/Users/po4yka/GitRep/bite-size-reader/docs/reference/cli-commands.md)

### Deliverables

- External-user documentation that does not require code reading to onboard.

## Phase 9: Testing and Rollout

### Objective

Release safely in stages and verify the external product surface end to end.

### TODO

- [ ] Add API tests for create/get/list aggregation session flows.
- [ ] Add auth tests for JWT-scoped aggregation access.
- [ ] Add CLI tests for command parsing, JSON output, and HTTP client integration.
- [ ] Add MCP tests for aggregation tools and request scoping.
- [ ] Add integration tests for one full end-to-end external aggregation request.
- [ ] Add metrics for aggregation API latency, completion rate, partial-success rate, and per-platform failure rate.
- [ ] Add metrics for CLI usage by command and MCP usage by tool.
- [ ] Roll out in stages:
  - [ ] internal users only
  - [ ] invite-only external CLI users
  - [ ] local MCP users
  - [ ] trusted hosted MCP beta
  - [ ] broad external enablement
- [ ] Review support load and error rates after each stage before widening.

### Deliverables

- A staged rollout with measurable safety checks.

## Recommended Execution Order

1. Phase 1: Public API Contract Hardening
2. Phase 2: Auth and External User Provisioning
3. Phase 3: CLI Aggregation MVP
4. Phase 4: Session Lifecycle and Long-Running Job Semantics
5. Phase 5: Local MCP Write Support
6. Phase 7: Security, Abuse Controls, and Cost Guardrails
7. Phase 8: Documentation and Integration Guides
8. Phase 6: Public Multi-User MCP Architecture
9. Phase 9: Testing and Rollout

## MVP Cut

If you need the fastest safe external launch, the MVP cut is:

- API create/get/list for aggregation sessions
- admin-issued client secrets for approved users
- `bsr aggregate` and `bsr aggregation get`
- polling-based session lifecycle
- local/trusted MCP only
- rate limits and basic quotas
- docs for onboarding and CLI usage

That gets external users working through CLI quickly without prematurely exposing hosted multi-user MCP.

## Definition of Done

- External users can authenticate without owner intervention at request time.
- External users can submit multi-source URL bundles from the CLI.
- External users can retrieve aggregation results and failures reliably.
- MCP supports aggregation for local/trusted users.
- Hosted MCP, if enabled, is request-scoped and multi-user safe.
- Aggregation traffic is rate-limited, audited, and observable.
- Documentation is sufficient for onboarding external users without source-code assistance.

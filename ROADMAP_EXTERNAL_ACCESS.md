# External Access Roadmap: CLI and MCP for Multi-Source Aggregation

## Status

Completed.

The external-access roadmap is implemented across the authenticated REST API, CLI, MCP tools/resources, request-scoped hosted MCP auth, deployment guardrails, observability, and rollout documentation.

## Delivered External Surface

### REST API

- `POST /v1/aggregations`
- `GET /v1/aggregations/{session_id}`
- `GET /v1/aggregations`

These endpoints are authenticated, user-scoped, URL-first for the public contract, and return lifecycle/progress/failure details for persisted aggregation sessions.

### CLI

Implemented commands:

- `bsr aggregate ...`
- `bsr aggregation get <session_id>`
- `bsr aggregation list --limit N --offset N`

The CLI is a thin authenticated API client and supports positional URLs, `--file`, `--lang`, repeatable `--hint`, human-readable output, and JSON output.

### MCP

Implemented tools:

- `create_aggregation_bundle`
- `get_aggregation_bundle`
- `list_aggregation_bundles`
- `check_source_supported`

Implemented resources:

- `bsr://aggregations/recent`
- `bsr://aggregations/{session_id}`

Note: the earlier proposed `bsr://aggregations/stats` resource was not shipped because instance-wide statistics are already exposed through the existing `bsr://stats` resource.

## Phase Status

### Phase 1: Public API Contract Hardening

Implemented.

- Public URL-first bundle request validation lives in `app/api/models/requests.py`.
- Create/get/list aggregation endpoints live in `app/api/routers/aggregation.py`.
- User scoping, response lifecycle states, progress payloads, and failure payloads are implemented.
- Public API docs and specs were updated in `docs/MOBILE_API_SPEC.md`, `docs/openapi/mobile_api.yaml`, `docs/openapi/mobile_api.json`, and `docs/SPEC.md`.

### Phase 2: Auth and External User Provisioning

Implemented.

- Secret-login auth, client typing, and provisioning rules live in `app/api/routers/auth/endpoints_secret_keys.py`, `app/api/routers/auth/dependencies.py`, and `app/api/routers/auth/tokens.py`.
- Owner/admin rotation and revoke flows are implemented.
- Supported client ID naming and secret lifecycle rules are documented in `docs/environment_variables.md`, `docs/SPEC.md`, and the external quickstart docs.
- Auth-side rate limits for secret login are configured and documented.

### Phase 3: CLI Aggregation MVP

Implemented.

- Client methods live in `clients/cli/src/bsr_cli/client.py`.
- Commands live in `clients/cli/src/bsr_cli/commands/aggregation.py`.
- Rendering lives in `clients/cli/src/bsr_cli/output.py`.
- CLI documentation lives in `clients/cli/README.md` and `docs/reference/cli-commands.md`.

### Phase 4: Session Lifecycle and Long-Running Job Semantics

Implemented.

- Lifecycle fields and progress tracking live in `app/db/_models_aggregation.py`, `app/db/migrations/022_add_aggregation_session_lifecycle.py`, and the aggregation session repository.
- End-to-end extraction and synthesis lifecycle behavior lives in `app/application/services/multi_source_aggregation_service.py`.
- Data-model and lifecycle semantics are documented in `docs/reference/data-model.md` and `docs/SPEC.md`.

### Phase 5: Local MCP Write Support

Implemented.

- MCP aggregation service lives in `app/mcp/aggregation_service.py`.
- Tool registration lives in `app/mcp/tool_registrations.py`.
- Resource registration lives in `app/mcp/resource_registrations.py`.
- Local/trusted MCP server wiring lives in `app/mcp/server.py` and `app/cli/mcp_server.py`.

### Phase 6: Public Multi-User MCP Architecture

Implemented.

- Request-scoped MCP identity resolution lives in `app/mcp/context.py`.
- Hosted MCP HTTP auth and forwarded-token support live in `app/mcp/http_auth.py`.
- Public SSE/hosted MCP behavior is documented in `docs/mcp_server.md`.
- Tests cover request-scoped auth and identity propagation in `tests/test_mcp_http_auth.py`, `tests/test_mcp_context.py`, `tests/test_mcp_resource_registrations.py`, and `tests/test_mcp_tool_registrations.py`.

### Phase 7: Security, Guardrails, and Operations

Implemented.

- Aggregation create rate limits and client-scoped limits live in `app/api/middleware.py` and `app/config/api.py`.
- SSRF guardrails for public bundle URLs live in `app/api/routers/aggregation.py`.
- Aggregation audit events and public-traffic guardrails are documented in `docs/DEPLOYMENT.md` and `docs/explanation/observability-strategy.md`.

### Phase 8: Documentation and External Onboarding

Implemented.

- External onboarding lives in `docs/tutorials/external-access-quickstart.md`.
- Hosted MCP usage docs live in `docs/mcp_server.md`.
- CLI docs live in `clients/cli/README.md` and `docs/reference/cli-commands.md`.
- API-facing docs live in `docs/MOBILE_API_SPEC.md`.
- Troubleshooting and operator rollout guidance live in `docs/TROUBLESHOOTING.md` and `docs/DEPLOYMENT.md`.

### Phase 9: Validation, Observability, and Rollout

Implemented.

- External aggregation request metrics and MCP tool metrics are emitted and covered by tests.
- End-to-end external aggregation API coverage exists in `tests/api/test_aggregation_api.py`.
- MCP surface coverage exists in `tests/test_mcp_aggregation_service.py`, `tests/test_mcp_resource_registrations.py`, `tests/test_mcp_tool_registrations.py`, `tests/test_mcp_http_auth.py`, and `tests/test_mcp_server.py`.
- Aggregation observability coverage exists in `tests/observability/test_aggregation_metrics.py`.
- Staged rollout guidance and promotion/rollback thresholds live in `docs/DEPLOYMENT.md`.

## Result

Completed.

- External users can authenticate, submit mixed-source URL bundles, poll persisted session results, and inspect prior sessions through the public API.
- The CLI exposes the same workflow without bypassing server-side auth, rollout, validation, or persistence.
- MCP supports local trusted write flows and request-scoped hosted public access without relying on the old process-scoped `MCP_USER_ID` model.

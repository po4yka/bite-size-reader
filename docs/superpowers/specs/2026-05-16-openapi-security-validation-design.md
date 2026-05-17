# OpenAPI Security Consistency Validation

**Date:** 2026-05-16  
**Status:** Approved

## Problem

The existing OpenAPI tests verify route coverage and schema shape, but nothing cross-checks whether a route protected in code (`Depends(get_current_user)`) actually declares `security: [{HTTPBearer: []}]` in `docs/openapi/mobile_api.yaml`. A new protected route can silently appear as public in the spec and downstream client generators.

## Goals

- Protected routes (using `get_current_user`) must declare `security:` in YAML.
- Public routes must be in an explicit allowlist; any unrecognized public route fails CI.
- Admin/system routes (using `require_owner`) must document a 403 response in YAML.
- Existing docs-sync checks remain intact.
- Clear failure messages with fix directives.

## Approach: FastAPI dependant-tree introspection

Walk each `APIRoute`'s `.dependant` dependency tree recursively. If `get_current_user` appears anywhere in the tree, the route is classified as "code-protected." Compare against the YAML spec's `security:` field on each operation.

`require_owner` is called inside handler bodies, not as a `Depends`, so it cannot be detected from the dependant tree. Proxy-detect owner-only routes via path prefix (`/v1/admin/`, `/v1/system/`) and assert they document a 403 response.

## New file: `tests/api/test_openapi_security.py`

### Fixtures

- `app_instance` — imports FastAPI app with minimal env vars (JWT/SECRET_KEY, no DB). Reuses the same monkeypatching pattern as `test_runtime_openapi_drift.py`.
- `yaml_spec` — loads `docs/openapi/mobile_api.yaml`.

### Helper: `_depends_on(dependant, target_fn) -> bool`

Recursive cycle-safe walk of FastAPI `Dependant` trees. Checks `dependant.call is target_fn` at each node; recurses into `dependant.dependencies`.

### Class `TestSecurityConsistency`

**`test_protected_routes_declare_security`**

1. Walk `app.routes`; for each `APIRoute`, call `_depends_on(route.dependant, get_current_user)`.
2. Collect all (METHOD, path) pairs classified as code-protected.
3. For each, look up the YAML operation and assert `security` is present and contains `{HTTPBearer: []}`.
4. Failure message: lists every offending route with instruction to add `security:\n  - HTTPBearer: []` to the YAML operation.

**`test_public_routes_are_allowlisted`**

1. Parse YAML paths; collect operations without a `security:` field.
2. Compare against `PUBLIC_ROUTES` frozenset.
3. Fail if any unrecognized route appears (route in YAML-public but not in allowlist).
4. Failure message: lists routes with instruction to either add security to YAML or add to `PUBLIC_ROUTES` in the test file.

**`test_allowlisted_routes_are_not_secured`** (inverse check)

1. Assert no route in `PUBLIC_ROUTES` has a `security:` declaration in the YAML.
2. Catches stale allowlist entries after a route is later secured.

**`test_owner_only_routes_document_403`**

1. For all YAML paths starting with `/v1/admin/` or `/v1/system/`, assert each operation documents a `"403"` response.
2. Failure message: lists routes missing 403 doc with instruction to add the response entry.

### `PUBLIC_ROUTES` allowlist (initial)

```python
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/health/detailed"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/metrics"),
    ("GET", "/v1/proxy/image"),
    ("POST", "/v1/auth/credentials-login"),
    ("POST", "/v1/auth/refresh"),
    ("POST", "/v1/auth/secret-login"),
    ("POST", "/v1/auth/telegram-login"),
})
```

## CI change: `.github/workflows/ci.yml`

Expand the existing "Check OpenAPI spec sync with code" step:

```yaml
- name: Check OpenAPI spec sync with code
  run: |
    pytest tests/api/test_openapi_sync.py tests/api/test_openapi_security.py \
      -v --tb=short
```

## Error message format

Each failure message follows the pattern:

```
<TestName>: <count> route(s) failed security consistency check:

  POST /v1/some/route
  GET  /v1/another/route

Fix: <actionable instruction>
```

## Out of scope

- Detecting `require_owner` calls inside handler bodies via AST parsing.
- Validating WebSocket routes (no standard OpenAPI security model).
- Owner-only annotation via custom `x-owner-only` YAML extension (future work).

## Files changed

| File | Change |
|------|--------|
| `tests/api/test_openapi_security.py` | New — security consistency tests |
| `.github/workflows/ci.yml` | Add new test file to OpenAPI sync step |

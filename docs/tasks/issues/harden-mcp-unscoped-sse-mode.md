---
title: Harden MCP unscoped SSE mode (env gate + bind 127.0.0.1)
status: backlog
area: api
priority: medium
owner: unassigned
blocks: []
blocked_by: []
created: 2026-05-17
updated: 2026-05-17
---

- [ ] #task Harden MCP unscoped SSE mode (env gate + bind 127.0.0.1) #repo/ratatoskr #area/api #status/backlog 🔼

## Objective

`app/mcp/server.py:89-149` permits `auth_mode="disabled"` and `allow_unscoped_sse=True`, logging only a warning that "MCP startup user scope is disabled; queries can access all users". The flag is intended for local debugging but is far too easy to leave on in production — anyone reaching the SSE port (Docker network, accidental binding, port-forward) reads cross-user data without auth.

## Context

- Startup branch: `app/mcp/server.py:89-149`.
- Aggregation service emits only a hint at `app/mcp/aggregation_service.py:70`.
- Comparable allowlist defaults elsewhere are fail-closed (`webapp_auth.py:60-104`, `dependencies.py:124-131`).

## Scope

- Require explicit `MCP_ALLOW_UNSCOPED_PRODUCTION=true` env var in addition to the existing CLI/config flag when `APP_ENV=production`.
- Emit `logger.error` (not warning) on startup with the resolved scope when unscoped.
- Bind to 127.0.0.1 unconditionally when unscoped — refuse to bind to a non-loopback interface unless the env gate is set.
- Add a Prometheus gauge `ratatoskr_mcp_unscoped_enabled` (0/1) and an alert when the gauge is 1 in production for more than 5 minutes.

## Acceptance criteria

- [ ] Production startup with `auth_mode="disabled"` and no `MCP_ALLOW_UNSCOPED_PRODUCTION=true` exits non-zero.
- [ ] Unscoped mode in dev binds to 127.0.0.1 by default.
- [ ] Gauge + alert in place.
- [ ] Test asserts the production startup failure path.

## References

- Startup: `app/mcp/server.py:89-149`
- Aggregation: `app/mcp/aggregation_service.py:70`
- MCP doc: `docs/reference/mcp-server.md`

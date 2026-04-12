# External Access Quickstart: CLI and MCP Aggregation

Use this guide when you already have a running Bite-Size Reader server and want to access mixed-source aggregation through the external API, packaged CLI, or hosted MCP surface.

**Time:** ~10 minutes  
**Audience:** External users, integrators, operators onboarding external users

## What You Need

Before you start, make sure you have:

- the server base URL, for example `https://bsr.example.com`
- your numeric `user_id`
- a client ID such as `cli-workstation-v1` or `mcp-agent-v1`
- the first client secret for that client ID

Operator notes:

- `SECRET_LOGIN_ENABLED=true` must be enabled on the API
- public deployments should set `ALLOWED_CLIENT_IDS` explicitly
- external self-service secret management is intentionally limited to `cli-*`, `mcp-*`, and `automation-*` client IDs

Credential notes:

- client secrets are shown in plaintext only when they are created or rotated
- a rotated secret immediately replaces the previous plaintext secret for future `secret-login` calls
- a revoked secret cannot mint new JWTs
- if you lose the first secret, ask the issuer for a new one or rotate it yourself if your deployment allows self-service secret rotation for that client type

## 1. Log In from the CLI

Point the CLI at your server and exchange the client secret for JWT tokens:

```bash
bsr config --url https://bsr.example.com

bsr login \
  --server https://bsr.example.com \
  --user-id 123456 \
  --client-id cli-workstation-v1 \
  --secret <paste-secret-once>

bsr whoami
```

What happens:

- `bsr login` calls `POST /v1/auth/secret-login`
- the CLI stores the returned access and refresh tokens in `~/.config/bsr/config.toml`
- the CLI refreshes the access token automatically when it is close to expiry
- if refresh later fails because the session was revoked or the refresh token was invalidated, run `bsr login` again with an active secret

## 2. Submit Your First Aggregation Bundle

Submit one or more URLs directly:

```bash
bsr aggregate \
  https://x.com/example/status/1 \
  https://www.youtube.com/watch?v=dQw4w9WgXcQ
```

You can also read URLs from a file and force the preferred output language:

```bash
bsr aggregate --file sources.txt --lang en
```

If the source mix is ambiguous, provide repeatable hints in the same order as the submitted URLs:

```bash
bsr aggregate \
  --hint x_post \
  --hint youtube_video \
  https://x.com/example/status/1 \
  https://youtu.be/dQw4w9WgXcQ
```

The command is currently blocking. It waits for extraction plus synthesis and returns the final server-side session snapshot on success.

## 3. Reopen the Session and List Recent Bundles

Use the session ID from the create response to revisit the persisted result later:

```bash
bsr aggregation get 42
bsr aggregation list --limit 20
```

Possible session statuses:

- `pending`
- `processing`
- `completed`
- `partial`
- `failed`

Useful fields to inspect:

- `progress.completionPercent`
- `successfulCount`
- `failedCount`
- `failure`
- `queuedAt`, `startedAt`, `completedAt`, `lastProgressAt`

## 4. Script with JSON Output

Every external CLI command supports `--json` for shell automation:

```bash
bsr --json aggregate --file sources.txt | jq '.session.sessionId'
bsr --json aggregation get 42 | jq '.session.progress'
bsr --json aggregation list --limit 5 | jq '.sessions[] | {id, status, progress}'
```

This is the recommended path for shell scripts and cron-style automation.

## 5. Connect a Local Agent over stdio

For same-machine or otherwise trusted local agent workflows, keep using the startup-scoped MCP mode:

```bash
MCP_USER_ID=123456 python -m app.cli.mcp_server
```

In this mode:

- `MCP_USER_ID` or `--user-id` sets the scoped user once at startup
- no per-request bearer auth is required
- read tools and aggregation tools both run as that one user

See [MCP Server](../mcp_server.md) for Claude Desktop and Docker examples.

## 6. Connect to Hosted Public MCP

Hosted public MCP uses the SSE transport and authenticates every request.

First mint an access token with the same secret-login flow:

```bash
curl -X POST https://bsr.example.com/v1/auth/secret-login \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": 123456,
    "client_id": "mcp-agent-v1",
    "secret": "<paste-secret-once>"
  }'
```

Then connect your MCP client to `https://bsr.example.com/sse` and send:

```http
Authorization: Bearer <access_token>
```

If your MCP client cannot attach bearer headers directly, terminate auth at a trusted gateway and forward:

```http
X-BSR-Forwarded-Access-Token: <original-access-token>
X-BSR-MCP-Forwarding-Secret: <shared-forwarding-secret>
```

Once connected, the typical aggregation workflow is:

1. Call `create_aggregation_bundle(...)`
2. Re-open a specific stored run with `get_aggregation_bundle(session_id)` or `bsr://aggregations/{session_id}`
3. Optionally inspect `list_aggregation_bundles(...)`
4. Read `bsr://aggregations/recent` for recent bundle context

See [MCP Server](../mcp_server.md) for full header and deployment guidance.

## 7. Recovery Paths

If something goes wrong:

- lost secret: ask for a new secret or rotate the existing one if your deployment allows it
- rotated or revoked secret: old plaintext secret will no longer work for new `secret-login` calls
- expired access token: refresh with `POST /v1/auth/refresh`, or let the CLI do it automatically
- revoked refresh session or logout: run `bsr login` again
- aggregation rejected before execution: check rollout gates, client allowlists, and submitted URLs

## Related Docs

- [CLI README](../../clients/cli/README.md)
- [Mobile API Spec](../MOBILE_API_SPEC.md)
- [MCP Server](../mcp_server.md)
- [Troubleshooting](../TROUBLESHOOTING.md)
- [Environment Variables](../environment_variables.md)

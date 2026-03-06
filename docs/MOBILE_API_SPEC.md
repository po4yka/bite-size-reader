# Mobile API Specification (Bite-Size Reader)

- Version: 1.1
- Last Updated: 2026-03-06
- Canonical machine-readable contract: `docs/openapi/mobile_api.yaml` and `docs/openapi/mobile_api.json`

## Overview

This document is a developer-facing summary of the mobile API implemented by the FastAPI app.

- Base API prefix: `/v1`
- Primary clients: mobile apps (Android/iOS/KMP), Telegram Mini App
- Envelope contract: all JSON business responses use `success`, `data`, `meta`, and standardized `error`
- OpenAPI source of truth: `docs/openapi/mobile_api.yaml`

## Base URLs

- Production: `https://bitsizereaderapi.po4yka.com`
- Local: `http://localhost:8000`

Examples:

- `GET http://localhost:8000/v1/summaries`
- `GET http://localhost:8000/health`

## Authentication Modes

Most `/v1/*` endpoints require bearer auth:

- Header: `Authorization: Bearer <access_token>`

Digest Mini App endpoints (`/v1/digest/*`) use Telegram WebApp authentication via initData (validated by the backend middleware/dependencies).

## Envelope and Error Contract

Success response shape:

```json
{
  "success": true,
  "data": {},
  "meta": {
    "timestamp": "2026-03-06T00:00:00Z",
    "version": "1.0"
  }
}
```

Error response shape:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request",
    "details": {},
    "correlation_id": "req_abc123"
  },
  "meta": {
    "timestamp": "2026-03-06T00:00:00Z",
    "version": "1.0"
  }
}
```

## Sync Model (Current)

Current sync uses explicit sessions and chunked/full + delta + apply endpoints:

1. `POST /v1/sync/sessions` to create/resume session
2. `GET /v1/sync/full?session_id=...&limit=...` for initial full data chunks
3. `GET /v1/sync/delta?session_id=...&cursor=...&limit=...` for incremental updates
4. `POST /v1/sync/apply` to send client-side changes back to server

## Search and Discovery Parameters

`GET /v1/search` supports:

- Required: `q`
- Pagination: `limit`, `offset`
- Ranking mode: `mode=auto|keyword|semantic|hybrid`
- Filters: `language`, `tags[]`, `domains[]`, `start_date`, `end_date`, `is_read`, `is_favorited`
- Threshold: `min_similarity`

`GET /v1/search/semantic` supports:

- Required: `q`
- Pagination: `limit`, `offset`
- Filters: `language`, `tags[]`, `domains[]`, `start_date`, `end_date`, `is_read`, `is_favorited`
- Scope: `user_scope`
- Threshold: `min_similarity`

## Collections Parameters

`GET /v1/collections` supports:

- `parent_id` (for subtree listing)
- `limit`
- `offset`

## Endpoint Index

### Platform and Health

- `GET /`
- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /health/detailed`
- `GET /metrics`

### Authentication

- `POST /v1/auth/telegram-login`
- `POST /v1/auth/google-login`
- `POST /v1/auth/apple-login`
- `POST /v1/auth/refresh`
- `POST /v1/auth/logout`
- `GET /v1/auth/me`
- `DELETE /v1/auth/me`
- `GET /v1/auth/sessions`
- `POST /v1/auth/secret-login`
- `GET /v1/auth/secret-keys`
- `POST /v1/auth/secret-keys`
- `POST /v1/auth/secret-keys/{key_id}/rotate`
- `POST /v1/auth/secret-keys/{key_id}/revoke`
- `GET /v1/auth/me/telegram`
- `POST /v1/auth/me/telegram/link`
- `POST /v1/auth/me/telegram/complete`
- `DELETE /v1/auth/me/telegram`

### Summaries and Articles

Canonical summary endpoints:

- `GET /v1/summaries`
- `GET /v1/summaries/by-url`
- `GET /v1/summaries/{summary_id}`
- `PATCH /v1/summaries/{summary_id}`
- `DELETE /v1/summaries/{summary_id}`
- `GET /v1/summaries/{summary_id}/content`
- `POST /v1/summaries/{summary_id}/favorite`

Alias endpoints for compatibility (`/v1/articles/*`) map to the same handlers:

- `GET /v1/articles`
- `GET /v1/articles/by-url`
- `GET /v1/articles/{summary_id}`
- `PATCH /v1/articles/{summary_id}`
- `DELETE /v1/articles/{summary_id}`
- `GET /v1/articles/{summary_id}/content`
- `POST /v1/articles/{summary_id}/favorite`

### Requests and Processing

- `POST /v1/requests`
- `GET /v1/requests/{request_id}`
- `GET /v1/requests/{request_id}/status`
- `POST /v1/requests/{request_id}/retry`
- `GET /v1/urls/check-duplicate`

### Search and Topics

- `GET /v1/search`
- `GET /v1/search/semantic`
- `GET /v1/search/insights`
- `GET /v1/topics/trending`
- `GET /v1/topics/related`

### Collections and Collaboration

- `GET /v1/collections`
- `POST /v1/collections`
- `GET /v1/collections/tree`
- `GET /v1/collections/{collection_id}`
- `PATCH /v1/collections/{collection_id}`
- `DELETE /v1/collections/{collection_id}`
- `POST /v1/collections/{collection_id}/move`
- `POST /v1/collections/{collection_id}/reorder`
- `GET /v1/collections/{collection_id}/items`
- `POST /v1/collections/{collection_id}/items`
- `DELETE /v1/collections/{collection_id}/items/{summary_id}`
- `POST /v1/collections/{collection_id}/items/reorder`
- `POST /v1/collections/{collection_id}/items/move`
- `POST /v1/collections/{collection_id}/share`
- `DELETE /v1/collections/{collection_id}/share/{target_user_id}`
- `GET /v1/collections/{collection_id}/acl`
- `POST /v1/collections/{collection_id}/invite`
- `POST /v1/collections/invites/{token}/accept`

### User Profile

- `GET /v1/user/preferences`
- `PATCH /v1/user/preferences`
- `GET /v1/user/stats`

### Notifications and Proxy

- `POST /v1/notifications/device`
- `GET /v1/proxy/image`

### Digest (Telegram Mini App)

- `GET /v1/digest/channels`
- `POST /v1/digest/channels/subscribe`
- `POST /v1/digest/channels/unsubscribe`
- `GET /v1/digest/preferences`
- `PATCH /v1/digest/preferences`
- `GET /v1/digest/history`
- `POST /v1/digest/trigger`
- `POST /v1/digest/trigger-channel`

### System Maintenance

- `GET /v1/system/db-dump`
- `HEAD /v1/system/db-dump`
- `GET /v1/system/db-info`
- `POST /v1/system/clear-cache`

## Notes

- Use OpenAPI for request and response schema details, enums, constraints, and examples.
- If this summary diverges from implementation, treat `docs/openapi/mobile_api.yaml` as authoritative.

# Mobile API Specification (Bite-Size Reader)

- Version: 1.0
- Last Updated: 2026-02-04
- Scope: Telegram-first pipeline exposed via FastAPI `/v1` for Android/iOS clients.

## Contract at a Glance

- Envelopes only: `success=true|false`, `data` or `error`, always return `meta.timestamp`, `meta.version`, `correlation_id` header + body on errors.
- Auth: JWT (Telegram login exchange + refresh).
- Typed responses across auth, summaries, requests, search, sync, user. Errors standardized for 401/403/404/409/410/422/429/500.
- Base URLs: prod `https://bitsizereaderapi.po4yka.com/v1`, local `http://localhost:8000/v1`.

```mermaid
sequenceDiagram
  participant App
  participant API as FastAPI /v1
  participant Pipeline as Router + UseCase
  participant Extract as Firecrawl/YouTube
  participant LLM as OpenRouter + Validators
  participant DB as SQLite
  App->>API: POST /requests (url|forward)
  API->>Pipeline: normalize + dedupe
  Pipeline->>Extract: fetch content
  Extract->>LLM: chunks → summary JSON
  LLM-->>Pipeline: contract-validated summary
  Pipeline->>DB: persist request/crawl/llm_call/summary
  Pipeline-->>API: response envelope
  API-->>App: data + correlation_id
```

## Authentication

- `POST /auth/telegram-login`: exchange Telegram auth payload → `{access_token, refresh_token, expires_in}`.
- `POST /auth/refresh`: refresh access token.
- Header: `Authorization: Bearer <access_token>`.

## Core Resources (minimal fields)

- Summaries
  - `GET /summaries`: list with `pagination{total,limit,offset,has_more}` and `stats{total_summaries,unread_count}`.
  - `GET /summaries/{id}`: full JSON payload (matches `app/core/summary_contract.py`).
  - `PATCH /summaries/{id}`: `is_read` updates.
- Requests
  - `POST /requests`: `{type: url|forward, input_url|content_text, lang_preference}` with dedupe hint and `estimated_wait_seconds`.
  - `GET /requests/{id}`: request + crawl + llm_calls + summary ids.
  - `GET /requests/{id}/status`: polling with `stage`, `progress`, `estimated_seconds_remaining`.
  - `POST /requests/{id}/retry`: create a retry request.
- Search & Topics
  - `GET /search?q=...`: FTS results + pagination.
  - `GET /topics/trending`, `GET /topics/related`: trending tags and related summaries.
- URL Utility
  - `GET /urls/check-duplicate`: `is_duplicate`, `existing_request_id/summary_id`.
- Collections
  - `GET /collections`: list user collections.
  - `POST /collections`: create a collection.
  - `GET /collections/{id}`: collection detail with items.
  - `PATCH /collections/{id}`: update collection.
  - `DELETE /collections/{id}`: delete collection.
  - `POST /collections/{id}/items`: add item to collection.
  - `DELETE /collections/{id}/items/{item_id}`: remove item.
- Health
  - `GET /health`: service health check (returns 200 when API is ready).
- Notifications
  - Notification endpoints for push and in-app alerts.
- System
  - `GET /system/info`: system information and version.
- User
  - `GET /user/preferences`, `PATCH /user/preferences`.
  - `GET /user/stats`.

## Sync Model (mobile-first)

- `GET /sync/full`: session with chunk URLs; params `since`, `chunk_size<=500`.
- `GET /sync/full/{sync_id}/chunk/{n}`: chunked payloads (summaries+requests+sources).
- `GET /sync/delta?since=`: `changes{created,updated,deleted}`, `sync_timestamp`, `has_more`, `next_since`.
- `POST /sync/upload-changes`: client changes with conflict results (server wins by default).

```mermaid
flowchart LR
  A[Mobile app] -->|/sync/full| B[Session + chunk URLs]
  A -->|chunk downloads| C[Local store]
  A -->|/sync/delta since=ts| D[Changes]
  A -->|/sync/upload-changes| E[Server apply + conflicts]
```

## Data Shapes (summary)

- Envelopes: `success`, `data`, `meta{timestamp,version}`; errors add `error{code,message,details?,correlation_id}`.
- Summary payload fields align with `summary_contract.py`: `summary_250`, `summary_1000`, `tldr`, `key_ideas[5]`, `topic_tags[#tag]`, `entities{people,organizations,locations}`, `estimated_reading_time_min`, `key_stats`, `readability`, `metadata`, `extractive_quotes`, `questions_answered`, `topic_taxonomy`, `hallucination_risk`, `confidence`, optional `insights`, `forwarded_post_extras`.
- Processing stats: `model`, `tokens_used`, `latency_ms`, `crawl_latency_ms`, `llm_latency_ms`, `cost_usd`.
- Request status: `status`, `stage in [pending,content_extraction,llm_summarization,validation,success,error]`, `can_retry`, `estimated_seconds_remaining`.

## Error Handling

- Codes: `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `DUPLICATE_URL`, `RATE_LIMIT_EXCEEDED`, `INTERNAL_ERROR`, `SERVICE_UNAVAILABLE`.
- Retry guidance: `429` respect `Retry-After`; `5xx` exponential backoff (2s,4s,8s,16s, max 4); `401/403` refresh auth; network errors same backoff.

## Rate Limiting (server guidance)

- Authenticated default: 100 rpm; summaries: 200 rpm; requests: 10 rpm; search: 50 rpm.
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`; `429` includes `retry_after`.

## Offline & Mobile Notes

- Initial sync: `/sync/full` chunks → store locally (Room); mark timestamp.
- Delta loop: `/sync/delta` then `/sync/upload-changes`; server wins on conflicts unless client is whitelisted per TD.
- Queue offline writes (mark read) and flush when online.

## Security

- JWT HS256 secret >=32 chars; enforce `ALLOWED_USER_IDS`; validate Telegram login hash.
- Redact `Authorization` in logs; include `X-Correlation-ID`.
- HTTPS in prod; CORS restricted; body limits (<=10 MB).

## Testing Expectations

- API: pytest/httpx for envelopes, auth, summaries CRUD, requests + polling, search, sync, rate limiting, error envelopes.
- Mobile: MockWebServer + Room; ensure envelope parsing and conflict handling.

---

## API Examples

### Base URL

**Production:** `https://bitsizereaderapi.po4yka.com/v1` (replace with your deployment)
**Local Development:** `http://localhost:8000/v1`

**Environment Variable Reference:**

```bash
API_BASE_URL=${API_HOST:-localhost}:${API_PORT:-8000}
```

---

### Authentication

#### 1. Telegram Login Exchange

**Request:**

```bash
curl -X POST http://localhost:8000/v1/auth/telegram-login \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_user_id": 123456789,
    "telegram_auth_token": "1a2b3c4d5e6f7g8h9i0j"
  }'
```

**Response:**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user_id": 123456789
  },
  "meta": {
    "timestamp": "2026-02-09T12:00:00Z",
    "version": "1.0"
  }
}
```

**Python:**

```python
import httpx

response = httpx.post(
    "http://localhost:8000/v1/auth/telegram-login",
    json={
        "telegram_user_id": 123456789,
        "telegram_auth_token": "1a2b3c4d5e6f7g8h9i0j"
    }
)
tokens = response.json()["data"]
access_token = tokens["access_token"]
```

**JavaScript:**

```javascript
const response = await fetch('http://localhost:8000/v1/auth/telegram-login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        telegram_user_id: 123456789,
        telegram_auth_token: '1a2b3c4d5e6f7g8h9i0j'
    })
});
const { data } = await response.json();
const accessToken = data.access_token;
```

---

#### 2. Refresh Access Token

**Request:**

```bash
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

**Response:**

```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600
  },
  "meta": {
    "timestamp": "2026-02-09T12:05:00Z",
    "version": "1.0"
  }
}
```

---

### Summaries

#### 3. List Summaries

**Request:**

```bash
curl -X GET "http://localhost:8000/v1/summaries?limit=10&offset=0" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Response:**

```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
        "url": "https://example.com/article",
        "title": "Example Article Title",
        "tldr": "Short summary of the article",
        "summary_250": "Concise 250-character summary...",
        "created_at": "2026-02-09T10:00:00Z",
        "is_read": false
      }
    ],
    "pagination": {
      "total": 150,
      "limit": 10,
      "offset": 0,
      "has_more": true
    },
    "stats": {
      "total_summaries": 150,
      "unread_count": 42
    }
  },
  "meta": {
    "timestamp": "2026-02-09T12:00:00Z",
    "version": "1.0"
  }
}
```

**Python:**

```python
response = httpx.get(
    "http://localhost:8000/v1/summaries",
    headers={"Authorization": f"Bearer {access_token}"},
    params={"limit": 10, "offset": 0}
)
summaries = response.json()["data"]["items"]
```

---

#### 4. Get Single Summary

**Request:**

```bash
curl -X GET http://localhost:8000/v1/summaries/a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6 \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Response:**

```json
{
  "success": true,
  "data": {
    "id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
    "url": "https://example.com/article",
    "title": "Example Article Title",
    "tldr": "Short summary",
    "summary_250": "Concise 250-character summary...",
    "summary_1000": "Detailed 1000-character summary...",
    "key_ideas": [
      "Main idea 1",
      "Main idea 2",
      "Main idea 3"
    ],
    "topic_tags": ["#technology", "#programming"],
    "entities": {
      "people": ["Person Name"],
      "organizations": ["Company Name"],
      "locations": ["City Name"]
    },
    "estimated_reading_time_min": 5,
    "confidence": 0.95,
    "created_at": "2026-02-09T10:00:00Z",
    "is_read": false
  },
  "meta": {
    "timestamp": "2026-02-09T12:00:00Z",
    "version": "1.0"
  }
}
```

---

#### 5. Update Summary (Mark as Read)

**Request:**

```bash
curl -X PATCH http://localhost:8000/v1/summaries/a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6 \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{"is_read": true}'
```

**Response:**

```json
{
  "success": true,
  "data": {
    "id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
    "is_read": true,
    "updated_at": "2026-02-09T12:01:00Z"
  },
  "meta": {
    "timestamp": "2026-02-09T12:01:00Z",
    "version": "1.0"
  }
}
```

---

### Sync

#### 6. Full Sync

**Request:**

```bash
curl -X POST "http://localhost:8000/v1/sync/summaries?mode=full" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Response:**

```json
{
  "success": true,
  "data": {
    "added": [
      {
        "id": "a1b2c3d4...",
        "url": "https://example.com/article1",
        "title": "Article 1",
        "created_at": "2026-02-08T10:00:00Z"
      }
    ],
    "modified": [],
    "deleted": [],
    "sync_timestamp": "2026-02-09T12:00:00Z",
    "stats": {
      "total_synced": 150,
      "added_count": 150,
      "modified_count": 0,
      "deleted_count": 0
    }
  },
  "meta": {
    "timestamp": "2026-02-09T12:00:00Z",
    "version": "1.0"
  }
}
```

---

#### 7. Delta Sync

**Request:**

```bash
curl -X POST "http://localhost:8000/v1/sync/summaries?mode=delta&last_sync_timestamp=2026-02-08T12:00:00Z" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Response:**

```json
{
  "success": true,
  "data": {
    "added": [
      {
        "id": "new-id-123",
        "url": "https://example.com/new-article",
        "title": "New Article",
        "created_at": "2026-02-09T10:00:00Z"
      }
    ],
    "modified": [
      {
        "id": "existing-id-456",
        "is_read": true,
        "updated_at": "2026-02-09T11:00:00Z"
      }
    ],
    "deleted": ["old-id-789"],
    "sync_timestamp": "2026-02-09T12:00:00Z",
    "stats": {
      "total_synced": 3,
      "added_count": 1,
      "modified_count": 1,
      "deleted_count": 1
    }
  },
  "meta": {
    "timestamp": "2026-02-09T12:00:00Z",
    "version": "1.0"
  }
}
```

---

### Error Responses

#### 401 Unauthorized

```json
{
  "success": false,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or expired token",
    "details": "Token expired at 2026-02-09T11:00:00Z",
    "correlation_id": "x1y2z3-a4b5-c6d7-e8f9-g0h1i2j3k4l5"
  },
  "meta": {
    "timestamp": "2026-02-09T12:00:00Z",
    "version": "1.0"
  }
}
```

**Solution:** Refresh token or re-login

---

#### 429 Rate Limit Exceeded

```json
{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded",
    "details": "Limit: 100 requests per minute",
    "retry_after": 45,
    "correlation_id": "x1y2z3-a4b5-c6d7-e8f9-g0h1i2j3k4l5"
  },
  "meta": {
    "timestamp": "2026-02-09T12:00:00Z",
    "version": "1.0"
  }
}
```

**Response Headers:**

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1675943445
Retry-After: 45
```

**Solution:** Wait 45 seconds before retrying

---

## Integration Patterns

### Authentication Flow

```mermaid
sequenceDiagram
    participant App
    participant Bot as Telegram Bot
    participant API

    App->>Bot: /mobile_login
    Bot->>App: Auth Token (5 min TTL)
    App->>API: POST /auth/telegram-login
    API->>App: JWT (access + refresh)
    App->>API: Authenticated requests
    Note over App,API: Token valid 1 hour
    App->>API: POST /auth/refresh (before expiry)
    API->>App: New access token
```

---

### Sync Flow (Mobile-First)

```mermaid
sequenceDiagram
    participant App
    participant API
    participant DB

    Note over App: First Launch
    App->>API: POST /sync/summaries?mode=full
    API->>DB: Fetch all summaries
    DB-->>API: 150 summaries
    API-->>App: All summaries + sync_timestamp
    App->>App: Store locally

    Note over App: Delta Sync (later)
    App->>API: POST /sync/summaries?mode=delta&last_sync=T1
    API->>DB: Fetch changes since T1
    DB-->>API: 3 new, 1 modified, 1 deleted
    API-->>App: Changes + sync_timestamp=T2
    App->>App: Apply changes locally

    Note over App: Offline Changes
    App->>App: Mark summary as read (offline)
    Note over App: Back Online
    App->>API: POST /sync/upload-changes
    API->>DB: Apply changes (server wins on conflict)
    API-->>App: Conflict resolution results
```

---

## Complete Client Example (Swift)

```swift
import Foundation

class BiteSizeAPIClient {
    let baseURL = "http://localhost:8000/v1"
    var accessToken: String?

    func login(telegramUserId: Int, authToken: String) async throws {
        let url = URL(string: "\(baseURL)/auth/telegram-login")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body = ["telegram_user_id": telegramUserId, "telegram_auth_token": authToken]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, _) = try await URLSession.shared.data(for: request)
        let response = try JSONDecoder().decode(LoginResponse.self, from: data)
        self.accessToken = response.data.access_token
    }

    func getSummaries(limit: Int = 20, offset: Int = 0) async throws -> [Summary] {
        guard let token = accessToken else { throw APIError.notAuthenticated }

        var components = URLComponents(string: "\(baseURL)/summaries")!
        components.queryItems = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)")
        ]

        var request = URLRequest(url: components.url!)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, _) = try await URLSession.shared.data(for: request)
        let response = try JSONDecoder().decode(SummariesResponse.self, from: data)
        return response.data.items
    }
}

// Usage
let client = BiteSizeAPIClient()
try await client.login(telegramUserId: 123456789, authToken: "1a2b3c4d...")
let summaries = try await client.getSummaries(limit: 10)
```

---

## See Also

- [First Mobile API Client Tutorial](tutorials/first-mobile-api-client.md) - Step-by-step guide
- [OpenAPI Schema](openapi/) - Machine-readable API spec
- [SPEC.md](SPEC.md) - Technical specification
- [TROUBLESHOOTING § Mobile API Issues](TROUBLESHOOTING.md#mobile-api-issues)

---

**Last Updated:** 2026-02-09

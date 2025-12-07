# Mobile API Specification for Bite-Size Reader

**Version:** 1.0
**Last Updated:** 2025-11-15
**Target Platform:** Android (compatible with iOS)

---

## Latest Updates (2025-12-07)

- OpenAPI `/v1` spec now uses typed envelopes for all 200 responses (auth, summaries, requests, search, sync, user) and standardizes error envelopes (401/403/404/409/410/422/429/500) with `correlation_id` and retry metadata.
- Added explicit schemas for summaries (list/detail), search/pagination, request submission/status, duplicate checks, user preferences/stats, and sync (session/full/delta/apply with conflict results).
- Sync endpoints document cursors (`since`, `next_since`), `server_version`, and tombstone handling; `apply` returns per-item statuses and conflicts.
- Servers section added for production/staging/local; array query parameters clarified as repeated keys (e.g., `tags=ai&tags=travel`).

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [API Endpoints](#api-endpoints)
4. [Database Sync](#database-sync)
5. [Data Models](#data-models)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Offline Support](#offline-support)
9. [Implementation Guide](#implementation-guide)

---

## Overview

The Bite-Size Reader Mobile API provides RESTful endpoints for:
- **Retrieving summaries** from the article database
- **Submitting new URLs** for processing
- **Tracking processing status** of submitted requests
- **Full database synchronization** for offline access
- **Search and filtering** across all summaries

### Base URL
```
Production: https://api.bite-size-reader.com/v1
Development: http://localhost:8000/v1
```

### Response Format
All responses are in JSON format with the following structure:

**Success Response:**
```json
{
  "success": true,
  "data": { ... },
  "meta": {
    "timestamp": "2025-11-15T10:00:00Z",
    "version": "1.0"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid URL format",
    "details": { ... },
    "correlation_id": "req-abc123"
  },
  "meta": {
    "timestamp": "2025-11-15T10:00:00Z",
    "version": "1.0"
  }
}
```

---

## Authentication

### Method: Bearer Token (JWT)

All API requests must include an `Authorization` header:

```
Authorization: Bearer <jwt_token>
```

### Obtaining a Token

#### POST `/auth/telegram-login`
Exchange Telegram user authentication data for a JWT token.

**Request:**
```json
{
  "telegram_user_id": 123456789,
  "auth_hash": "abc123...",
  "timestamp": 1700000000
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 3600,
    "token_type": "Bearer"
  }
}
```

#### POST `/auth/refresh`
Refresh an expired access token.

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "expires_in": 3600
  }
}
```

---

## API Endpoints

### 1. Summary Management

#### GET `/summaries`
Retrieve a paginated list of summaries.

**Query Parameters:**
- `limit` (int, default=20, max=100) - Items per page
- `offset` (int, default=0) - Pagination offset
- `is_read` (bool, optional) - Filter by read status
- `lang` (string, optional) - Filter by language (`en`, `ru`)
- `start_date` (ISO 8601, optional) - Filter by creation date (from)
- `end_date` (ISO 8601, optional) - Filter by creation date (to)
- `sort` (string, default="created_at_desc") - Sort order: `created_at_desc`, `created_at_asc`

**Response:**
```json
{
  "success": true,
  "data": {
    "summaries": [
      {
        "id": 42,
        "request_id": 100,
        "title": "Article Title",
        "domain": "example.com",
        "url": "https://example.com/article",
        "tldr": "Brief summary of the article...",
        "summary_250": "Short 250-char summary...",
        "reading_time_min": 5,
        "topic_tags": ["#blockchain", "#crypto", "#technology"],
        "is_read": false,
        "lang": "en",
        "created_at": "2025-11-15T10:00:00Z",
        "confidence": 0.92,
        "hallucination_risk": "low"
      }
    ],
    "pagination": {
      "total": 247,
      "limit": 20,
      "offset": 0,
      "has_more": true
    },
    "stats": {
      "total_summaries": 247,
      "unread_count": 42
    }
  }
}
```

---

#### GET `/summaries/{summary_id}`
Retrieve a single summary with full details.

**Path Parameters:**
- `summary_id` (int, required) - Summary ID

**Response:**
```json
{
  "success": true,
  "data": {
    "summary": {
      "id": 42,
      "request_id": 100,
      "lang": "en",
      "is_read": false,
      "version": 1,
      "created_at": "2025-11-15T10:00:00Z",
      "json_payload": {
        "summary_250": "...",
        "summary_1000": "...",
        "tldr": "...",
        "key_ideas": [
          "Key idea 1",
          "Key idea 2",
          "Key idea 3",
          "Key idea 4",
          "Key idea 5"
        ],
        "topic_tags": ["#blockchain", "#crypto"],
        "entities": {
          "people": ["Satoshi Nakamoto"],
          "organizations": ["Bitcoin Foundation"],
          "locations": ["San Francisco"]
        },
        "estimated_reading_time_min": 5,
        "key_stats": [
          {
            "label": "Bitcoin Price",
            "value": 45000.50,
            "unit": "USD",
            "source_excerpt": "Bitcoin reached $45k today..."
          }
        ],
        "readability": {
          "method": "Flesch-Kincaid",
          "score": 45.2,
          "level": "College"
        },
        "metadata": {
          "title": "Understanding Bitcoin",
          "canonical_url": "https://example.com/bitcoin",
          "domain": "example.com",
          "author": "John Doe",
          "published_at": "2025-11-10T08:00:00Z"
        },
        "extractive_quotes": [
          {
            "text": "Bitcoin is a decentralized digital currency...",
            "source_span": "Introduction, paragraph 2"
          }
        ],
        "questions_answered": [
          {
            "question": "What is Bitcoin?",
            "answer": "Bitcoin is a decentralized digital currency..."
          }
        ],
        "topic_taxonomy": [
          {
            "label": "Blockchain",
            "score": 0.95,
            "path": "Technology/Cryptocurrency/Blockchain"
          }
        ],
        "hallucination_risk": "low",
        "confidence": 0.92,
        "insights": {
          "topic_overview": "This article explains Bitcoin basics...",
          "new_facts": [
            {
              "fact": "Bitcoin's market cap exceeded $1 trillion",
              "why_it_matters": "Milestone for cryptocurrency adoption",
              "confidence": 0.85
            }
          ],
          "open_questions": ["What will regulation look like?"],
          "caution": "Article may have pro-crypto bias"
        }
      }
    },
    "request": {
      "id": 100,
      "type": "url",
      "status": "success",
      "input_url": "https://example.com/bitcoin",
      "normalized_url": "https://example.com/bitcoin",
      "correlation_id": "req-abc123",
      "created_at": "2025-11-15T09:55:00Z"
    },
    "source": {
      "url": "https://example.com/bitcoin",
      "title": "Understanding Bitcoin",
      "domain": "example.com",
      "author": "John Doe",
      "published_at": "2025-11-10T08:00:00Z",
      "http_status": 200
    },
    "processing": {
      "model": "qwen/qwen3-max",
      "tokens_used": 2800,
      "cost_usd": 0.045,
      "latency_ms": 5740,
      "crawl_latency_ms": 2340,
      "llm_latency_ms": 3400
    }
  }
}
```

---

#### PATCH `/summaries/{summary_id}`
Update summary metadata (e.g., mark as read).

**Path Parameters:**
- `summary_id` (int, required) - Summary ID

**Request:**
```json
{
  "is_read": true
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 42,
    "is_read": true,
    "updated_at": "2025-11-15T10:05:00Z"
  }
}
```

---

#### DELETE `/summaries/{summary_id}`
Delete a summary (soft delete - marks as archived).

**Path Parameters:**
- `summary_id` (int, required) - Summary ID

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 42,
    "deleted_at": "2025-11-15T10:10:00Z"
  }
}
```

---

### 2. Request Submission & Status

#### POST `/requests`
Submit a new URL or forwarded message for processing.

**Request (URL):**
```json
{
  "type": "url",
  "input_url": "https://example.com/article",
  "lang_preference": "auto"
}
```

**Request (Forward):**
```json
{
  "type": "forward",
  "content_text": "Full text of forwarded message...",
  "forward_metadata": {
    "from_chat_id": 123456,
    "from_message_id": 789,
    "from_chat_title": "Tech Channel",
    "forwarded_at": "2025-11-15T09:50:00Z"
  },
  "lang_preference": "auto"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "request_id": 100,
    "correlation_id": "req-abc123",
    "type": "url",
    "status": "pending",
    "estimated_wait_seconds": 15,
    "created_at": "2025-11-15T09:55:00Z",
    "is_duplicate": false
  }
}
```

**Response (Duplicate Detected):**
```json
{
  "success": true,
  "data": {
    "is_duplicate": true,
    "existing_request_id": 99,
    "existing_summary_id": 41,
    "message": "This URL was already summarized",
    "summarized_at": "2025-11-14T15:30:00Z"
  }
}
```

---

#### GET `/requests/{request_id}`
Get details about a specific request.

**Path Parameters:**
- `request_id` (int, required) - Request ID

**Response:**
```json
{
  "success": true,
  "data": {
    "request": {
      "id": 100,
      "type": "url",
      "status": "success",
      "correlation_id": "req-abc123",
      "input_url": "https://example.com/article",
      "normalized_url": "https://example.com/article",
      "dedupe_hash": "abc123def456...",
      "created_at": "2025-11-15T09:55:00Z",
      "lang_detected": "en"
    },
    "crawl_result": {
      "status": "success",
      "http_status": 200,
      "latency_ms": 2340,
      "error": null
    },
    "llm_calls": [
      {
        "id": 1,
        "model": "qwen/qwen3-max",
        "status": "success",
        "tokens_prompt": 2500,
        "tokens_completion": 300,
        "cost_usd": 0.045,
        "latency_ms": 3400,
        "created_at": "2025-11-15T09:57:00Z"
      }
    ],
    "summary": {
      "id": 42,
      "status": "success",
      "created_at": "2025-11-15T10:00:00Z"
    }
  }
}
```

---

#### GET `/requests/{request_id}/status`
Poll for real-time processing status.

**Path Parameters:**
- `request_id` (int, required) - Request ID

**Response (Processing):**
```json
{
  "success": true,
  "data": {
    "request_id": 100,
    "status": "processing",
    "stage": "llm_summarization",
    "progress": {
      "current_step": 3,
      "total_steps": 4,
      "percentage": 75
    },
    "estimated_seconds_remaining": 8,
    "updated_at": "2025-11-15T09:58:30Z"
  }
}
```

**Possible Stages:**
- `pending` - Queued, waiting to start
- `content_extraction` - Extracting content via Firecrawl
- `llm_summarization` - Generating summary via LLM
- `validation` - Validating summary contract
- `success` - Processing complete
- `error` - Processing failed

**Response (Error):**
```json
{
  "success": true,
  "data": {
    "request_id": 100,
    "status": "error",
    "error_stage": "content_extraction",
    "error_type": "http_timeout",
    "error_message": "Request to URL timed out after 60 seconds",
    "can_retry": true,
    "correlation_id": "req-abc123"
  }
}
```

---

#### POST `/requests/{request_id}/retry`
Retry a failed request.

**Path Parameters:**
- `request_id` (int, required) - Request ID to retry

**Response:**
```json
{
  "success": true,
  "data": {
    "new_request_id": 101,
    "correlation_id": "req-abc123-retry-1",
    "status": "pending",
    "created_at": "2025-11-15T10:05:00Z"
  }
}
```

---

### 3. Search & Discovery

#### GET `/search`
Full-text search across all summaries using FTS5.

**Query Parameters:**
- `q` (string, required) - Search query
- `limit` (int, default=20, max=100) - Max results
- `offset` (int, default=0) - Pagination offset

**Search Syntax:**
- Wildcard: `bitcoin*`
- Phrase: `"artificial intelligence"`
- Boolean: `blockchain AND crypto`
- Exclusion: `crypto NOT bitcoin`

**Response:**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "request_id": 100,
        "summary_id": 42,
        "url": "https://example.com/bitcoin",
        "title": "Understanding Bitcoin",
        "domain": "example.com",
        "snippet": "...Bitcoin is a decentralized digital currency...",
        "tldr": "Brief overview of Bitcoin technology",
        "published_at": "2025-11-10T08:00:00Z",
        "created_at": "2025-11-15T10:00:00Z",
        "relevance_score": 0.95,
        "topic_tags": ["#blockchain", "#crypto"],
        "is_read": false
      }
    ],
    "pagination": {
      "total": 42,
      "limit": 20,
      "offset": 0,
      "has_more": true
    },
    "query": "blockchain"
  }
}
```

---

#### GET `/topics/trending`
Get trending topic tags across recent summaries.

**Query Parameters:**
- `limit` (int, default=20) - Max tags to return
- `days` (int, default=30) - Look back N days

**Response:**
```json
{
  "success": true,
  "data": {
    "tags": [
      {
        "tag": "#blockchain",
        "count": 42,
        "trend": "up",
        "percentage_change": 15.5
      },
      {
        "tag": "#cryptocurrency",
        "count": 38,
        "trend": "stable",
        "percentage_change": 0.2
      },
      {
        "tag": "#ai",
        "count": 35,
        "trend": "down",
        "percentage_change": -8.3
      }
    ],
    "time_range": {
      "start": "2025-10-16T00:00:00Z",
      "end": "2025-11-15T23:59:59Z"
    }
  }
}
```

---

#### GET `/topics/related`
Get summaries related to a specific topic tag.

**Query Parameters:**
- `tag` (string, required) - Topic tag (with or without #)
- `limit` (int, default=20) - Max results
- `offset` (int, default=0) - Pagination offset

**Response:**
```json
{
  "success": true,
  "data": {
    "tag": "#blockchain",
    "summaries": [
      {
        "summary_id": 42,
        "title": "Understanding Bitcoin",
        "tldr": "...",
        "created_at": "2025-11-15T10:00:00Z"
      }
    ],
    "pagination": {
      "total": 42,
      "limit": 20,
      "offset": 0
    }
  }
}
```

---

### 4. URL Utilities

#### GET `/urls/check-duplicate`
Check if a URL has already been summarized.

**Query Parameters:**
- `url` (string, required) - URL to check
- `include_summary` (bool, default=false) - Include full summary data

**Response (Not Duplicate):**
```json
{
  "success": true,
  "data": {
    "is_duplicate": false,
    "normalized_url": "https://example.com/article",
    "dedupe_hash": "abc123def456..."
  }
}
```

**Response (Duplicate Found):**
```json
{
  "success": true,
  "data": {
    "is_duplicate": true,
    "request_id": 100,
    "summary_id": 42,
    "summarized_at": "2025-11-15T10:00:00Z",
    "summary": {
      "title": "Article Title",
      "tldr": "...",
      "url": "https://example.com/article"
    }
  }
}
```

---

### 5. User Preferences & Stats

#### GET `/user/preferences`
Get user preferences.

**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": 123456789,
    "telegram_username": "johndoe",
    "lang_preference": "en",
    "notification_settings": {
      "enabled": true,
      "frequency": "daily"
    },
    "app_settings": {
      "theme": "dark",
      "font_size": "medium"
    }
  }
}
```

---

#### PATCH `/user/preferences`
Update user preferences.

**Request:**
```json
{
  "lang_preference": "en",
  "notification_settings": {
    "enabled": false
  },
  "app_settings": {
    "theme": "light"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "updated_fields": ["lang_preference", "notification_settings.enabled", "app_settings.theme"],
    "updated_at": "2025-11-15T10:10:00Z"
  }
}
```

---

#### GET `/user/stats`
Get user statistics.

**Response:**
```json
{
  "success": true,
  "data": {
    "total_summaries": 247,
    "unread_count": 42,
    "read_count": 205,
    "total_reading_time_min": 1235,
    "average_reading_time_min": 5,
    "favorite_topics": [
      {"tag": "#blockchain", "count": 35},
      {"tag": "#crypto", "count": 28},
      {"tag": "#technology", "count": 25}
    ],
    "favorite_domains": [
      {"domain": "medium.com", "count": 42},
      {"domain": "github.com", "count": 35}
    ],
    "language_distribution": {
      "en": 200,
      "ru": 47
    },
    "joined_at": "2024-01-01T00:00:00Z",
    "last_summary_at": "2025-11-15T10:00:00Z"
  }
}
```

---

## Database Sync

### Full Database Synchronization

The API supports full database synchronization for offline access on mobile devices.

#### GET `/sync/full`
Download the entire database in incremental chunks.

**Query Parameters:**
- `since` (ISO 8601, optional) - Only sync changes since this timestamp
- `chunk_size` (int, default=100, max=500) - Items per chunk

**Response:**
```json
{
  "success": true,
  "data": {
    "sync_id": "sync-xyz789",
    "timestamp": "2025-11-15T10:15:00Z",
    "total_items": 247,
    "chunks": 3,
    "download_urls": [
      "/sync/full/sync-xyz789/chunk/1",
      "/sync/full/sync-xyz789/chunk/2",
      "/sync/full/sync-xyz789/chunk/3"
    ],
    "expires_at": "2025-11-15T11:15:00Z"
  }
}
```

---

#### GET `/sync/full/{sync_id}/chunk/{chunk_number}`
Download a specific chunk of the database.

**Path Parameters:**
- `sync_id` (string, required) - Sync session ID
- `chunk_number` (int, required) - Chunk number (1-based)

**Response:**
```json
{
  "success": true,
  "data": {
    "sync_id": "sync-xyz789",
    "chunk_number": 1,
    "total_chunks": 3,
    "items": [
      {
        "summary": {
          "id": 42,
          "request_id": 100,
          "json_payload": { ... },
          "is_read": false,
          "lang": "en",
          "created_at": "2025-11-15T10:00:00Z"
        },
        "request": {
          "id": 100,
          "type": "url",
          "status": "success",
          "input_url": "https://example.com/article",
          "normalized_url": "https://example.com/article",
          "created_at": "2025-11-15T09:55:00Z"
        },
        "source": {
          "title": "Article Title",
          "domain": "example.com",
          "author": "John Doe",
          "published_at": "2025-11-10T08:00:00Z"
        }
      }
    ]
  }
}
```

---

#### GET `/sync/delta`
Get incremental updates since last sync.

**Query Parameters:**
- `since` (ISO 8601, required) - Last sync timestamp
- `limit` (int, default=100, max=500) - Max items to return

**Response:**
```json
{
  "success": true,
  "data": {
    "changes": {
      "created": [
        {
          "summary_id": 43,
          "created_at": "2025-11-15T10:20:00Z",
          "data": { ... }
        }
      ],
      "updated": [
        {
          "summary_id": 42,
          "updated_at": "2025-11-15T10:15:00Z",
          "changes": {
            "is_read": true
          }
        }
      ],
      "deleted": [
        {
          "summary_id": 41,
          "deleted_at": "2025-11-15T10:10:00Z"
        }
      ]
    },
    "sync_timestamp": "2025-11-15T10:25:00Z",
    "has_more": false
  }
}
```

---

#### POST `/sync/upload-changes`
Upload local changes from mobile device to server.

**Request:**
```json
{
  "changes": [
    {
      "summary_id": 42,
      "action": "update",
      "fields": {
        "is_read": true
      },
      "client_timestamp": "2025-11-15T10:05:00Z"
    }
  ],
  "device_id": "android-device-123",
  "last_sync": "2025-11-15T09:00:00Z"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "applied_changes": 1,
    "conflicts": [],
    "sync_timestamp": "2025-11-15T10:30:00Z"
  }
}
```

---

## Data Models

### Summary (Compact)
Used in list views.

```typescript
interface SummaryCompact {
  id: number;
  request_id: number;
  title: string;
  domain: string;
  url: string;
  tldr: string;
  summary_250: string;
  reading_time_min: number;
  topic_tags: string[];
  is_read: boolean;
  lang: "en" | "ru" | "auto";
  created_at: string; // ISO 8601
  confidence: number; // 0.0 - 1.0
  hallucination_risk: "low" | "med" | "high";
}
```

### Summary (Full)
Used in detail views.

```typescript
interface SummaryFull {
  id: number;
  request_id: number;
  lang: string;
  is_read: boolean;
  version: number;
  created_at: string;
  json_payload: SummaryPayload;
}

interface SummaryPayload {
  summary_250: string;
  summary_1000: string;
  tldr: string;
  key_ideas: string[];
  topic_tags: string[];
  entities: {
    people: string[];
    organizations: string[];
    locations: string[];
  };
  estimated_reading_time_min: number;
  key_stats: KeyStat[];
  readability: Readability;
  metadata: ArticleMetadata;
  extractive_quotes: Quote[];
  questions_answered: QA[];
  topic_taxonomy: TopicLabel[];
  hallucination_risk: "low" | "med" | "high";
  confidence: number;
  insights?: Insights;
  forwarded_post_extras?: ForwardedExtras;
}

interface KeyStat {
  label: string;
  value: number;
  unit: string;
  source_excerpt: string;
}

interface Readability {
  method: string;
  score: number;
  level: string;
}

interface ArticleMetadata {
  title: string;
  canonical_url: string;
  domain: string;
  author?: string;
  published_at?: string;
  last_updated?: string;
}

interface Quote {
  text: string;
  source_span: string;
}

interface QA {
  question: string;
  answer: string;
}

interface TopicLabel {
  label: string;
  score: number;
  path: string;
}

interface Insights {
  topic_overview: string;
  new_facts: NewFact[];
  open_questions: string[];
  caution?: string;
}

interface NewFact {
  fact: string;
  why_it_matters: string;
  confidence: number;
}
```

### Request

```typescript
interface Request {
  id: number;
  type: "url" | "forward";
  status: "pending" | "processing" | "success" | "error";
  correlation_id: string;
  input_url?: string;
  normalized_url?: string;
  dedupe_hash?: string;
  lang_detected?: string;
  created_at: string;
}
```

### Processing Status

```typescript
interface ProcessingStatus {
  request_id: number;
  status: "pending" | "processing" | "success" | "error";
  stage?: "content_extraction" | "llm_summarization" | "validation";
  progress?: {
    current_step: number;
    total_steps: number;
    percentage: number;
  };
  estimated_seconds_remaining?: number;
  error_message?: string;
  can_retry?: boolean;
  updated_at: string;
}
```

---

## Error Handling

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid input data |
| `UNAUTHORIZED` | 401 | Missing or invalid auth token |
| `FORBIDDEN` | 403 | User not allowed (not in whitelist) |
| `NOT_FOUND` | 404 | Resource not found |
| `DUPLICATE_URL` | 409 | URL already summarized |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |
| `SERVICE_UNAVAILABLE` | 503 | External service down (Firecrawl/OpenRouter) |

### Error Response Format

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid URL format",
    "details": {
      "field": "input_url",
      "constraint": "must be a valid HTTP/HTTPS URL"
    },
    "correlation_id": "req-abc123",
    "timestamp": "2025-11-15T10:00:00Z"
  }
}
```

### Retry Logic

**Recommended retry strategy for mobile clients:**

```
- 401/403: Don't retry, refresh auth token
- 429: Retry after delay specified in Retry-After header
- 5xx: Exponential backoff (2s, 4s, 8s, 16s) up to 4 retries
- Network errors: Exponential backoff up to 4 retries
```

---

## Rate Limiting

### Limits

- **Authenticated users:** 100 requests per minute
- **Summary retrieval:** 200 requests per minute
- **Request submission:** 10 requests per minute
- **Search:** 50 requests per minute

### Response Headers

All responses include rate limit headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1700000000
```

When rate limit is exceeded:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{
  "success": false,
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Try again in 60 seconds.",
    "retry_after": 60
  }
}
```

---

## Offline Support

### Sync Strategy for Android App

#### Initial Sync
1. Call `GET /sync/full` to get sync session
2. Download all chunks sequentially
3. Store in local SQLite database (Room)
4. Cache images and media locally
5. Mark sync timestamp

#### Incremental Sync
1. Call `GET /sync/delta?since={last_sync_timestamp}`
2. Apply changes to local database
3. Upload local changes via `POST /sync/upload-changes`
4. Handle conflicts (server wins by default)

#### Offline Operations
**Supported:**
- View all synced summaries
- Mark summaries as read (queued)
- Search local database
- Filter by tags, dates, read status

**Queued for online:**
- Submit new URL requests
- Upload "mark as read" changes
- Retry failed requests

#### Background Sync
Use Android WorkManager to:
- Sync delta changes every 15-60 minutes (when on WiFi)
- Upload queued changes when network available
- Download new summaries in background

---

## Implementation Guide

### Backend Implementation

**Recommended Stack:**
- **Framework:** FastAPI (Python)
- **Database:** SQLite (existing)
- **Auth:** JWT with PyJWT
- **API Docs:** Auto-generated via FastAPI (OpenAPI/Swagger)

**Steps:**
1. Create FastAPI app with routers for each endpoint group
2. Implement JWT auth middleware
3. Create Pydantic models for request/response validation
4. Wire up to existing database models (Peewee ORM)
5. Add CORS middleware for web clients
6. Deploy with Uvicorn + Nginx

**Example FastAPI Route:**

```python
from fastapi import APIRouter, Depends, HTTPException
from app.api.routers.auth import get_current_user
from app.db.models import Summary, Request

router = APIRouter(prefix="/summaries", tags=["summaries"])

@router.get("/{summary_id}")
async def get_summary(
    summary_id: int,
    user: User = Depends(get_current_user)
):
    summary = Summary.select().where(Summary.id == summary_id).first()
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")

    return {
        "success": True,
        "data": {
            "summary": summary.to_dict(),
            "request": summary.request.to_dict()
        }
    }
```

---

### Android Implementation

**Recommended Stack:**
- **HTTP Client:** Retrofit 2 + OkHttp
- **JSON Parsing:** Moshi or Gson
- **Local Database:** Room (SQLite)
- **Async:** Kotlin Coroutines + Flow
- **DI:** Hilt
- **Sync:** WorkManager

**Architecture:**
```
UI Layer (Jetpack Compose)
    ↓
ViewModel (LiveData/StateFlow)
    ↓
Repository (Single source of truth)
    ↓
┌─────────────┴─────────────┐
│                           │
API Service           Room Database
(Retrofit)            (Local cache)
```

**Example Retrofit Service:**

```kotlin
interface BiteReaderApi {
    @GET("summaries")
    suspend fun getSummaries(
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
        @Query("is_read") isRead: Boolean? = null
    ): ApiResponse<SummaryListResponse>

    @GET("summaries/{id}")
    suspend fun getSummary(
        @Path("id") summaryId: Int
    ): ApiResponse<SummaryDetailResponse>

    @PATCH("summaries/{id}")
    suspend fun updateSummary(
        @Path("id") summaryId: Int,
        @Body update: SummaryUpdate
    ): ApiResponse<SummaryUpdateResponse>

    @POST("requests")
    suspend fun submitRequest(
        @Body request: SubmitRequestBody
    ): ApiResponse<SubmitRequestResponse>

    @GET("requests/{id}/status")
    suspend fun getRequestStatus(
        @Path("id") requestId: Int
    ): ApiResponse<RequestStatusResponse>
}
```

**Example Room Entity:**

```kotlin
@Entity(tableName = "summaries")
data class SummaryEntity(
    @PrimaryKey val id: Int,
    @ColumnInfo(name = "request_id") val requestId: Int,
    @ColumnInfo(name = "json_payload") val jsonPayload: String,
    @ColumnInfo(name = "is_read") val isRead: Boolean,
    @ColumnInfo(name = "lang") val lang: String,
    @ColumnInfo(name = "created_at") val createdAt: String,
    @ColumnInfo(name = "synced_at") val syncedAt: Long
)

@Dao
interface SummaryDao {
    @Query("SELECT * FROM summaries WHERE is_read = 0 ORDER BY created_at DESC")
    fun getUnreadSummaries(): Flow<List<SummaryEntity>>

    @Query("SELECT * FROM summaries WHERE id = :id")
    suspend fun getSummaryById(id: Int): SummaryEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertSummaries(summaries: List<SummaryEntity>)

    @Query("UPDATE summaries SET is_read = :isRead WHERE id = :id")
    suspend fun updateReadStatus(id: Int, isRead: Boolean)
}
```

**Example Repository:**

```kotlin
class SummaryRepository(
    private val api: BiteReaderApi,
    private val dao: SummaryDao,
    private val syncManager: SyncManager
) {
    fun getUnreadSummaries(): Flow<List<Summary>> {
        return dao.getUnreadSummaries().map { entities ->
            entities.map { it.toDomain() }
        }
    }

    suspend fun getSummary(id: Int): Result<Summary> {
        // Try local first
        val local = dao.getSummaryById(id)
        if (local != null) {
            return Result.success(local.toDomain())
        }

        // Fetch from API
        return try {
            val response = api.getSummary(id)
            if (response.success) {
                val entity = response.data.toEntity()
                dao.insertSummaries(listOf(entity))
                Result.success(entity.toDomain())
            } else {
                Result.failure(ApiException(response.error))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    suspend fun markAsRead(id: Int) {
        // Update local immediately
        dao.updateReadStatus(id, true)

        // Queue sync
        syncManager.queueChange(
            SyncChange(
                summaryId = id,
                action = SyncAction.UPDATE,
                fields = mapOf("is_read" to true)
            )
        )
    }
}
```

---

## Testing

### API Testing

**Tools:**
- Postman collection (provided)
- pytest + httpx for integration tests
- Swagger UI at `/docs`

**Test Coverage:**
- Authentication flow
- CRUD operations for summaries
- Request submission and polling
- Search functionality
- Sync endpoints
- Error handling
- Rate limiting

### Android Testing

**Unit Tests:**
- Repository logic
- ViewModel state management
- Data mappers

**Integration Tests:**
- API client with MockWebServer
- Room database operations

**UI Tests:**
- Jetpack Compose UI tests
- End-to-end user flows

---

## Security Considerations

1. **Authentication:**
   - JWT tokens with short expiry (1 hour)
   - Refresh token rotation
   - Secure token storage on Android (EncryptedSharedPreferences)

2. **Authorization:**
   - Verify user is in `ALLOWED_USER_IDS` whitelist
   - Validate Telegram user ID matches token

3. **Input Validation:**
   - Validate all URLs before processing
   - Sanitize search queries
   - Limit request body size (10 MB max)

4. **Data Privacy:**
   - No PII stored (only Telegram user IDs)
   - Redact Authorization headers in logs
   - Encrypt local database on Android

5. **Rate Limiting:**
   - Per-user rate limits
   - IP-based fallback limits
   - CAPTCHA for suspicious activity

---

## Versioning

API versioning via URL path: `/v1/`, `/v2/`

**Backward Compatibility:**
- New fields are added without breaking existing clients
- Deprecated fields are marked but not removed for 6 months
- Breaking changes require new API version

---

## Support & Debugging

### Correlation IDs

All requests should include a correlation ID for tracing:

**Request Header:**
```
X-Correlation-ID: mobile-android-123456789-1700000000-abc123
```

**Response Header:**
```
X-Correlation-ID: mobile-android-123456789-1700000000-abc123
```

Use this ID for support requests and error reporting.

### Debug Mode

Enable debug logging on Android:

```kotlin
val logging = HttpLoggingInterceptor().apply {
    level = if (BuildConfig.DEBUG) {
        HttpLoggingInterceptor.Level.BODY
    } else {
        HttpLoggingInterceptor.Level.NONE
    }
}

val okHttp = OkHttpClient.Builder()
    .addInterceptor(logging)
    .build()
```

---

## Changelog

### Version 1.0 (2025-11-15)
- Initial API specification
- Full database sync support
- Search and discovery endpoints
- User preferences and stats
- Mobile-optimized responses

---

## Appendix: Example Workflows

### Workflow 1: First-Time App Launch

1. User opens app
2. App prompts for Telegram login
3. User authenticates via Telegram
4. App receives JWT token from `POST /auth/telegram-login`
5. App calls `GET /sync/full` to download all summaries
6. App downloads chunks and stores in Room database
7. App displays unread summaries from local database

### Workflow 2: Submit New URL

1. User pastes URL in app
2. App calls `GET /urls/check-duplicate?url=...`
3. If not duplicate:
   - App calls `POST /requests` with URL
   - App receives `request_id`
   - App polls `GET /requests/{id}/status` every 2 seconds
   - When status = "success", app calls `GET /summaries/{id}`
   - App displays summary
4. If duplicate:
   - App shows "Already summarized" message
   - App navigates to existing summary

### Workflow 3: Offline Read

1. User opens app without network
2. App loads summaries from Room database
3. User reads summary
4. App marks as read locally
5. App queues sync change
6. When network returns, app calls `POST /sync/upload-changes`
7. Server updates `is_read` flag

### Workflow 4: Background Sync

1. WorkManager schedules periodic sync every 30 minutes
2. Worker calls `GET /sync/delta?since={last_sync}`
3. Worker applies changes to Room database
4. Worker uploads queued changes via `POST /sync/upload-changes`
5. Worker updates last sync timestamp
6. Worker shows notification if new summaries available

---

**End of Mobile API Specification**

For questions or support, refer to:
- Main documentation: `README.md`
- Technical spec: `SPEC.md`
- AI assistant guide: `CLAUDE.md`

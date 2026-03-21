# Enhanced Admin Panel

**Status:** Partial (basic DB stats only)
**Complexity:** Medium
**Dependencies:** None

## Problem Statement

BSR's admin panel (`web/src/features/admin/AdminPage.tsx`) only shows database file size and table row counts with a cache-clear button. There is no visibility into background jobs, user activity, content health, or system metrics. Karakeep provides user management, job monitoring, broken link detection, and detailed system overview.

## Current State

Existing admin capabilities:

- `GET /v1/admin/db-info` -- DB file size, table row counts
- `POST /v1/admin/cache/clear` -- clear Redis cache
- Web page at `/web/admin` -- renders the above

## Enhancements

### 1. User Management

BSR supports multiple users via `ALLOWED_USER_IDS`. The admin panel should show all users.

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/users` | List all users with stats |

**Response:**

```json
{
    "users": [
        {
            "user_id": 123456789,
            "username": "john",
            "is_owner": true,
            "summary_count": 342,
            "request_count": 380,
            "tag_count": 25,
            "collection_count": 8,
            "storage_used_bytes": 52428800,
            "last_active_at": "2026-03-20T15:30:00Z",
            "created_at": "2025-06-01T10:00:00Z"
        }
    ],
    "total_users": 3
}
```

**Frontend:** Carbon `DataTable` with sortable columns. No user CRUD -- user management is via `ALLOWED_USER_IDS` env var.

### 2. Background Job Monitoring

BSR uses APScheduler for background tasks (digest scheduling, backups, RSS polling). The admin panel should surface job status.

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/jobs` | List background job status |
| `GET` | `/v1/admin/jobs/history` | Recent job execution history |

**Data Sources:**

- APScheduler job store (running/pending/paused jobs)
- `ImportJob` table (import job status)
- Pipeline stats: aggregate from `requests` table (pending/processing/completed/failed counts)
- `DigestDelivery` table (digest job status)

**Response:**

```json
{
    "scheduler": {
        "running": true,
        "jobs": [
            {
                "id": "digest_scheduler",
                "name": "Channel Digest Scheduler",
                "next_run": "2026-03-21T18:00:00Z",
                "status": "active"
            }
        ]
    },
    "pipeline": {
        "pending_requests": 3,
        "processing_requests": 1,
        "completed_today": 45,
        "failed_today": 2,
        "avg_processing_time_ms": 8500
    },
    "imports": {
        "active_jobs": 0,
        "completed_today": 1
    }
}
```

**Frontend:** Dashboard cards showing job counts, status indicators (green/yellow/red), and a jobs table.

### 3. Content Health

Surface content quality issues: failed crawls, broken URLs, validation errors.

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/health/content` | Content health report |
| `POST` | `/v1/admin/health/recheck` | Trigger URL recheck for failed items |

**Response:**

```json
{
    "total_summaries": 1200,
    "total_requests": 1350,
    "failed_requests": 47,
    "failed_by_error_type": {
        "timeout": 12,
        "extraction_failed": 18,
        "llm_error": 8,
        "network": 9
    },
    "recent_failures": [
        {
            "request_id": 456,
            "url": "https://example.com/broken",
            "error_type": "timeout",
            "error_message": "Scraper chain exhausted",
            "created_at": "2026-03-20T14:00:00Z"
        }
    ]
}
```

**Frontend:** Error breakdown chart (Carbon chart or simple bars), recent failures table with "Retry" action button.

### 4. System Metrics

Aggregate operational metrics from existing data.

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/metrics` | System metrics |

**Response:**

```json
{
    "database": {
        "file_size_bytes": 104857600,
        "table_counts": { "requests": 1350, "summaries": 1200, "tags": 150 }
    },
    "search": {
        "fts5_indexed": 1200,
        "chroma_documents": 1150,
        "chroma_collection_size_bytes": 52428800
    },
    "cache": {
        "redis_connected": true,
        "keys_count": 450,
        "memory_used_bytes": 10485760
    },
    "scraper_chain": {
        "success_rate_7d": {
            "scrapling": 0.85,
            "defuddle": 0.72,
            "firecrawl": 0.91,
            "playwright": 0.78,
            "direct_html": 0.65
        }
    },
    "llm": {
        "total_calls_7d": 380,
        "avg_latency_ms": 3200,
        "total_tokens_7d": 2500000,
        "total_cost_usd_7d": 1.45,
        "error_rate_7d": 0.02
    }
}
```

**Frontend:** Metric cards with sparklines, scraper chain success rates as horizontal bar chart.

### 5. Audit Log Viewer

BSR already has an `AuditLog` model. Surface it in the admin UI.

**API Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/admin/audit-log` | Paginated audit log. Query params: `action`, `user_id`, `since`, `limit`, `offset` |

**Frontend:** Carbon `DataTable` with filters for action type and user. Columns: timestamp, user, action, details.

## Architecture

All admin endpoints are protected by `is_owner=True` check on the authenticated user. No new models needed -- all data comes from aggregating existing tables.

### Key Files to Modify

- `app/api/routers/system.py` -- extend with admin endpoints (or create `app/api/routers/admin.py`)
- `web/src/features/admin/AdminPage.tsx` -- expand with new sections

### Admin Page Layout

```
+-----------------------------------------------+
|  Admin Dashboard                               |
+-----------------------------------------------+
|  [Users] [Jobs] [Health] [Metrics] [Audit Log] |  <- Carbon Tabs
+-----------------------------------------------+

Tab: Users
  DataTable: user list with stats

Tab: Jobs
  Dashboard cards: pipeline stats
  DataTable: scheduled jobs
  DataTable: recent job history

Tab: Health
  Error breakdown summary
  DataTable: recent failures with retry button

Tab: Metrics
  Metric cards: DB size, search stats, cache
  Scraper success rates chart
  LLM usage summary

Tab: Audit Log
  Filterable DataTable: audit events
```

## Frontend Components

- **AdminDashboard** (`web/src/features/admin/AdminDashboard.tsx`) -- tab container
- **AdminUsers** (`web/src/features/admin/AdminUsers.tsx`) -- user table
- **AdminJobs** (`web/src/features/admin/AdminJobs.tsx`) -- job monitoring
- **AdminHealth** (`web/src/features/admin/AdminHealth.tsx`) -- content health
- **AdminMetrics** (`web/src/features/admin/AdminMetrics.tsx`) -- system metrics
- **AdminAuditLog** (`web/src/features/admin/AdminAuditLog.tsx`) -- audit log viewer

## Telegram Bot Integration

- `/admin` -- show summary stats (users, summaries, pending requests, error rate)
- `/admin jobs` -- show background job status
- `/admin errors` -- show recent failure count

## Testing

- API integration tests for each admin endpoint
- Access control test: non-owner user gets 403
- Metrics aggregation test: verify counts match direct DB queries

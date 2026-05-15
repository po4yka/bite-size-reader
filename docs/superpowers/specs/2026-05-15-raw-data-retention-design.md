# Raw Data Retention & Purge — Design Spec

**Date:** 2026-05-15
**Status:** Approved

## Problem

Ratatoskr persists large raw artifacts indefinitely: full Telegram message payloads,
scraped HTML/markdown, complete LLM request/response bodies, and video transcripts.
These fields have no user-visible value after a summary is produced and represent
both a storage cost and a privacy risk. Summaries, cost metrics, and search metadata
must be preserved.

## Goal

Implement configurable, per-subsystem TTL-based nulling of raw artifact fields.
Purge runs on a schedule, is idempotent, and never removes user-visible summary data.

---

## Approach: Field-level nulling via scheduled Taskiq task

Raw content columns are SET to NULL once they age past their configured TTL.
The containing row is never deleted — metadata, cost data, and status fields survive.
All targeted columns are already `nullable=True`; no Alembic migration is required.

---

## Section 1: Configuration

**New file:** `app/config/retention.py`

Pattern: identical to `app/config/background.py` (Pydantic BaseSettings, validation_alias env vars).

```python
class RetentionConfig(BaseSettings):
    enabled: bool           # RETENTION_ENABLED          default: True
    cron: str               # RETENTION_CRON             default: "0 3 * * *"  (3am UTC)
    batch_size: int         # RETENTION_BATCH_SIZE       default: 500

    telegram_raw_days: int        # RETENTION_TELEGRAM_RAW_DAYS       default: 30
    crawl_content_days: int       # RETENTION_CRAWL_CONTENT_DAYS      default: 7
    llm_payload_days: int         # RETENTION_LLM_PAYLOAD_DAYS        default: 90
    video_transcript_days: int    # RETENTION_VIDEO_TRANSCRIPT_DAYS   default: 30
    interaction_text_days: int    # RETENTION_INTERACTION_TEXT_DAYS   default: 30
    request_content_days: int     # RETENTION_REQUEST_CONTENT_DAYS    default: 30
```

`RetentionConfig` is added to `AppConfig` under the `retention` field.

**Semantics:** TTL of `0` means "never purge this subsystem." Each subsystem is
independently skippable.

---

## Section 2: Fields Targeted Per Subsystem

| Subsystem key | Table | Columns NULLed | Preserved columns |
|---|---|---|---|
| `telegram_raw` | `telegram_messages` | `text_full`, `entities_json`, `telegram_raw_json` | `message_id`, `chat_id`, `date_ts`, `media_type`, `forward_*` |
| `crawl_content` | `crawl_results` | `content_markdown`, `content_html`, `raw_response_json`, `firecrawl_details_json`, `structured_json`, `metadata_json`, `links_json` | `source_url`, `http_status`, `status`, `latency_ms`, `endpoint` |
| `llm_payload` | `llm_calls` | `request_messages_json`, `request_headers_json`, `response_text`, `response_json`, `openrouter_response_text`, `openrouter_response_json` | `model`, `tokens_prompt`, `tokens_completion`, `cost_usd`, `latency_ms`, `status`, `attempt_index`, `attempt_trigger` |
| `video_transcript` | `video_downloads` | `transcript_text` | all other fields |
| `interaction_text` | `user_interactions` | `input_text` | all other fields |
| `request_content` | `requests` | `content_text`, `error_context_json` | all other fields |

---

## Section 3: Purge Task

**New file:** `app/tasks/purge_raw_data.py`

**Task name:** `ratatoskr.data.purge`

**Pattern:** mirrors `app/tasks/reconcile_vector_index.py` exactly.

### Return type

```python
@dataclass
class PurgeStats:
    telegram_raw: int
    crawl_content: int
    llm_payload: int
    video_transcript: int
    interaction_text: int
    request_content: int
```

### Per-subsystem SQL pattern

Most tables use their own `created_at` as the age reference:

```sql
UPDATE <table>
SET <col1> = NULL, <col2> = NULL, ...
WHERE id IN (
    SELECT id FROM <table>
    WHERE created_at < NOW() - INTERVAL '<n> days'
      AND (<col1> IS NOT NULL OR <col2> IS NOT NULL OR ...)
    LIMIT <batch_size>
)
```

Two exceptions:

- **`crawl_results`** has no `created_at` — use `updated_at` instead.
- **`telegram_messages`** has no timestamp column — join to the parent `requests.created_at`:

```sql
UPDATE telegram_messages
SET text_full = NULL, entities_json = NULL, telegram_raw_json = NULL
WHERE id IN (
    SELECT tm.id FROM telegram_messages tm
    JOIN requests r ON r.id = tm.request_id
    WHERE r.created_at < NOW() - INTERVAL '<n> days'
      AND (tm.text_full IS NOT NULL
           OR tm.entities_json IS NOT NULL
           OR tm.telegram_raw_json IS NOT NULL)
    LIMIT <batch_size>
)
```

The `IS NOT NULL` guard makes every run idempotent: already-purged rows produce
zero rowcount and cost nothing on re-runs.

`result.rowcount` (SQLAlchemy) provides the per-subsystem count in `PurgeStats`.

### Safety

- Redis distributed lock key: `task_lock:data_purge`, TTL 600s (10 min)
- Subsystem skipped entirely when its configured TTL is `0`
- Batch ceiling prevents lock timeout on large backlogs; next cron tick continues

---

## Section 4: Scheduler Integration

`app/tasks/scheduler.py` — add to `_AppConfigScheduleSource._build_tasks()`:

```python
if cfg.retention.enabled:
    tasks.append(
        ScheduledTask(
            task_name="ratatoskr.data.purge",
            cron=cfg.retention.cron,
            labels={"job": "data_purge"},
            args=[], kwargs={},
        )
    )
```

---

## Section 5: Tests

**File:** `tests/tasks/test_purge_raw_data.py`

Six subsystem tests + two cross-cutting tests.

### Subsystem test shape (repeated for each of the six)

1. Insert `Request` + child row with `created_at` backdated past TTL (via `tests/db_helpers.py`)
2. Insert second row within TTL
3. Call `_purge_body()` directly (not via broker)
4. Assert: expired row's raw fields are `None`; preserved fields unchanged
5. Assert: in-TTL row completely untouched
6. Re-run `_purge_body()` — assert returned count is `0` (idempotency)

### Cross-cutting tests

- **TTL = 0:** configure one subsystem with `days=0`; assert no rows updated
- **enabled = False:** `RetentionConfig(enabled=False)`; assert zero updates across all subsystems

---

## Section 6: Documentation

`docs/reference/environment-variables.md` — new `## Data Retention` section:

```
RETENTION_ENABLED                  bool    true    Master switch
RETENTION_CRON                     str     "0 3 * * *"  UTC cron
RETENTION_BATCH_SIZE               int     500     Max rows per subsystem per run
RETENTION_TELEGRAM_RAW_DAYS        int     30      0 = never purge
RETENTION_CRAWL_CONTENT_DAYS       int     7       0 = never purge
RETENTION_LLM_PAYLOAD_DAYS         int     90      0 = never purge
RETENTION_VIDEO_TRANSCRIPT_DAYS    int     30      0 = never purge
RETENTION_INTERACTION_TEXT_DAYS    int     30      0 = never purge
RETENTION_REQUEST_CONTENT_DAYS     int     30      0 = never purge
```

---

## What Is Never Purged

- `summaries.json_payload` — canonical summary (user-visible archive)
- `summary_embeddings` — vector search index
- `collections`, `tags`, `highlights`, `feedbacks` — user content
- All row-level metadata: IDs, timestamps, status, cost fields, correlation IDs

---

## Acceptance Criteria

1. Raw fields per subsystem are NULLed after their configured TTL passes
2. Purge is idempotent: re-running produces zero updates on already-purged rows
3. TTL `= 0` disables purge for that subsystem
4. No summary row, embedding, or user-visible data is modified
5. Tests cover at least one raw field per subsystem
6. New env vars documented in `docs/reference/environment-variables.md`

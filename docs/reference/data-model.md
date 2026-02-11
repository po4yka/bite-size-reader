# Data Model Reference

Complete reference for Bite-Size Reader's SQLite database schema.

**Audience:** Developers, Database Administrators
**Type:** Reference
**Related:** [SPEC.md § Data Model](../SPEC.md#data-model-sqlite), [How to Backup and Restore](../how-to/backup-and-restore.md)

---

## Overview

Bite-Size Reader uses **SQLite** as its persistence layer with 21 model classes managed by Peewee ORM.

**Database Location:** `DB_PATH` environment variable (default: `/data/app.db`)

**ORM:** Peewee
**Migrations:** Manual SQL files in `app/cli/migrations/`

---

## Core Tables

### users

**Purpose:** Telegram users who have interacted with the bot.

**Schema:**

```sql
CREATE TABLE users (
    telegram_user_id  INTEGER PRIMARY KEY,
    username          TEXT,
    first_name        TEXT,
    last_name         TEXT,
    language_code     TEXT,
    is_owner          INTEGER DEFAULT 0,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `telegram_user_id` (int, PK) - Telegram user ID
- `username` (str, nullable) - Telegram @username
- `first_name` (str, nullable) - User's first name
- `last_name` (str, nullable) - User's last name
- `language_code` (str, nullable) - Telegram language code (e.g., `en`, `ru`)
- `is_owner` (bool) - True if user ID in `ALLOWED_USER_IDS`
- `created_at` (datetime) - First interaction timestamp
- `updated_at` (datetime) - Last update timestamp

**Indexes:**

- Primary key on `telegram_user_id`

**Relationships:**

- One-to-many with `requests`
- One-to-many with `user_interactions`
- One-to-many with `user_devices`

---

### chats

**Purpose:** Telegram chats (private DMs, groups, channels) where bot is active.

**Schema:**

```sql
CREATE TABLE chats (
    chat_id     INTEGER PRIMARY KEY,
    type        TEXT NOT NULL,  -- 'private', 'group', 'supergroup', 'channel'
    title       TEXT,
    username    TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `chat_id` (int, PK) - Telegram chat ID
- `type` (str) - Chat type (`private`, `group`, `supergroup`, `channel`)
- `title` (str, nullable) - Chat title (for groups/channels)
- `username` (str, nullable) - Chat @username
- `created_at` (datetime) - First interaction timestamp

**Indexes:**

- Primary key on `chat_id`

**Relationships:**

- One-to-many with `requests`
- One-to-many with `telegram_messages`

---

### requests

**Purpose:** One row per user submission (URL or forwarded message).

**Schema:**

```sql
CREATE TABLE requests (
    id                         TEXT PRIMARY KEY,
    created_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    type                       TEXT NOT NULL,  -- 'url' | 'forward'
    status                     TEXT DEFAULT 'pending',  -- 'pending'| 'ok' |'error'
    chat_id                    INTEGER REFERENCES chats(chat_id),
    user_id                    INTEGER REFERENCES users(telegram_user_id),
    input_url                  TEXT,
    normalized_url             TEXT,
    dedupe_hash                TEXT,  -- sha256(normalized_url)
    input_message_id           INTEGER,
    fwd_from_chat_id           INTEGER,
    fwd_from_msg_id            INTEGER,
    lang_detected              TEXT,  -- 'en', 'ru', etc.
    route_version              INTEGER DEFAULT 1,
    total_processing_time_sec  REAL,
    error_message              TEXT
);
```

**Fields:**

- `id` (str, PK) - Unique request ID (correlation ID)
- `created_at` (datetime) - Request creation timestamp
- `type` (str) - Request type (`url` or `forward`)
- `status` (str) - Processing status (`pending`, `ok`, `error`)
- `chat_id` (int, FK) - Foreign key to `chats`
- `user_id` (int, FK) - Foreign key to `users`
- `input_url` (str, nullable) - Original URL as submitted
- `normalized_url` (str, nullable) - Normalized URL (lowercased, params sorted)
- `dedupe_hash` (str, nullable) - SHA256 hash of `normalized_url` for deduplication
- `input_message_id` (int, nullable) - Telegram message ID
- `fwd_from_chat_id` (int, nullable) - Forwarded from chat ID
- `fwd_from_msg_id` (int, nullable) - Forwarded message ID
- `lang_detected` (str, nullable) - Detected language code
- `route_version` (int) - Message router version
- `total_processing_time_sec` (float, nullable) - End-to-end processing time
- `error_message` (str, nullable) - Error details if `status='error'`

**Indexes:**

```sql
CREATE INDEX idx_requests_user_id ON requests(user_id);
CREATE INDEX idx_requests_created_at ON requests(created_at);
CREATE INDEX idx_requests_dedupe_hash ON requests(dedupe_hash);
CREATE INDEX idx_requests_status ON requests(status);
```

**Relationships:**

- Many-to-one with `users`
- Many-to-one with `chats`
- One-to-one with `telegram_messages`
- One-to-one with `crawl_results`
- One-to-one with `video_downloads`
- One-to-many with `llm_calls`
- One-to-one with `summaries`

---

### telegram_messages

**Purpose:** Full Telegram message snapshot for audit trail.

**Schema:**

```sql
CREATE TABLE telegram_messages (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id                TEXT UNIQUE REFERENCES requests(id),
    message_id                INTEGER,
    chat_id                   INTEGER,
    user_id                   INTEGER,
    date_ts                   INTEGER,  -- Unix timestamp
    text_full                 TEXT,
    entities_json             TEXT,  -- JSON array of message entities
    media_type                TEXT,  -- 'photo', 'video', 'document', etc.
    media_file_ids_json       TEXT,  -- JSON array of file IDs
    forward_from_chat_id      INTEGER,
    forward_from_chat_type    TEXT,
    forward_from_chat_title   TEXT,
    forward_from_message_id   INTEGER,
    forward_date_ts           INTEGER,
    message_snapshot          TEXT,  -- Full Pyrogram Message JSON
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `request_id` (str, FK, unique) - Foreign key to `requests`
- `message_id` (int) - Telegram message ID
- `chat_id` (int) - Telegram chat ID
- `user_id` (int) - Telegram user ID
- `date_ts` (int) - Message timestamp (Unix epoch)
- `text_full` (str, nullable) - Full message text
- `entities_json` (str, nullable) - JSON array of message entities (mentions, URLs, etc.)
- `media_type` (str, nullable) - Media type if present
- `media_file_ids_json` (str, nullable) - JSON array of file IDs
- `forward_from_chat_id` (int, nullable) - Forwarded from chat ID
- `forward_from_chat_type` (str, nullable) - Forwarded from chat type
- `forward_from_chat_title` (str, nullable) - Forwarded from chat title
- `forward_from_message_id` (int, nullable) - Forwarded message ID
- `forward_date_ts` (int, nullable) - Original forward timestamp
- `message_snapshot` (str) - Full Pyrogram Message object as JSON
- `created_at` (datetime) - Record creation timestamp

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_telegram_messages_request_id ON telegram_messages(request_id);
CREATE INDEX idx_telegram_messages_message_id ON telegram_messages(message_id);
```

**Relationships:**

- One-to-one with `requests`

---

### crawl_results

**Purpose:** Firecrawl API responses for content extraction.

**Schema:**

```sql
CREATE TABLE crawl_results (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id               TEXT UNIQUE REFERENCES requests(id),
    source_url               TEXT NOT NULL,
    endpoint                 TEXT DEFAULT '/v2/scrape',
    http_status              INTEGER,
    status                   TEXT,  -- 'ok'|'error'
    options_json             TEXT,  -- Firecrawl request options
    content_markdown         TEXT,  -- Extracted markdown content
    content_html             TEXT,  -- Extracted HTML content
    structured_json          TEXT,  -- Structured data extraction result
    metadata_json            TEXT,  -- Page metadata (title, description, etc.)
    links_json               TEXT,  -- Extracted links
    screenshots_paths_json   TEXT,  -- Screenshot file paths
    firecrawl_success        INTEGER,  -- 0/1 boolean
    firecrawl_error_code     TEXT,
    firecrawl_error_message  TEXT,
    firecrawl_details_json   TEXT,  -- Error details
    raw_response_json        TEXT,  -- Full Firecrawl response (legacy)
    tokens_used              INTEGER,
    latency_ms               INTEGER,
    error_text               TEXT,  -- Internal error message
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `request_id` (str, FK, unique) - Foreign key to `requests`
- `source_url` (str) - URL crawled
- `endpoint` (str) - Firecrawl endpoint (`/v2/scrape`)
- `http_status` (int, nullable) - HTTP response status code
- `status` (str) - Internal status (`ok` or `error`)
- `options_json` (str, nullable) - Firecrawl request options as JSON
- `content_markdown` (str, nullable) - Extracted markdown content
- `content_html` (str, nullable) - Extracted HTML content
- `structured_json` (str, nullable) - Structured data extraction
- `metadata_json` (str, nullable) - Page metadata (title, description, og tags, etc.)
- `links_json` (str, nullable) - Extracted links as JSON array
- `screenshots_paths_json` (str, nullable) - Screenshot file paths
- `firecrawl_success` (bool) - Firecrawl success flag
- `firecrawl_error_code` (str, nullable) - Firecrawl error code
- `firecrawl_error_message` (str, nullable) - Firecrawl error message
- `firecrawl_details_json` (str, nullable) - Firecrawl error details
- `raw_response_json` (str, nullable) - Full Firecrawl response (legacy)
- `tokens_used` (int, nullable) - Tokens consumed
- `latency_ms` (int, nullable) - API call latency
- `error_text` (str, nullable) - Internal error message
- `created_at` (datetime) - Record creation timestamp

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_crawl_results_request_id ON crawl_results(request_id);
```

**Relationships:**

- One-to-one with `requests`

---

### video_downloads

**Purpose:** YouTube video downloads and transcript extraction.

**Schema:**

```sql
CREATE TABLE video_downloads (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id                 TEXT UNIQUE REFERENCES requests(id),
    created_at                 TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    video_id                   TEXT NOT NULL,  -- YouTube video ID (11 chars)
    status                     TEXT DEFAULT 'pending',  -- 'pending'| 'downloading' | 'completed' |'error'
    video_file_path            TEXT,
    subtitle_file_path         TEXT,
    metadata_file_path         TEXT,
    thumbnail_file_path        TEXT,
    title                      TEXT,
    channel                    TEXT,
    channel_id                 TEXT,
    duration_sec               INTEGER,
    upload_date                TEXT,  -- YYYYMMDD format
    view_count                 INTEGER,
    like_count                 INTEGER,
    resolution                 TEXT,  -- '1080p', '720p', etc.
    file_size_bytes            INTEGER,
    video_codec                TEXT,  -- 'avc1', 'vp9', etc.
    audio_codec                TEXT,  -- 'mp4a', 'opus', etc.
    format_id                  TEXT,  -- yt-dlp format ID
    transcript_text            TEXT,  -- Full transcript
    transcript_source          TEXT,  -- 'youtube-transcript-api' | 'yt-dlp-subtitles'
    subtitle_language          TEXT,  -- 'en', 'ru', etc.
    auto_generated             INTEGER,  -- 0/1 boolean
    download_started_at        TIMESTAMP,
    download_completed_at      TIMESTAMP,
    error_text                 TEXT
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `request_id` (str, FK, unique) - Foreign key to `requests`
- `created_at` (datetime) - Record creation timestamp
- `video_id` (str) - YouTube video ID (11 characters)
- `status` (str) - Download status
- `video_file_path` (str, nullable) - Path to downloaded MP4 file
- `subtitle_file_path` (str, nullable) - Path to subtitle/caption VTT file
- `metadata_file_path` (str, nullable) - Path to yt-dlp metadata JSON
- `thumbnail_file_path` (str, nullable) - Path to thumbnail image
- `title` (str, nullable) - Video title
- `channel` (str, nullable) - Channel name
- `channel_id` (str, nullable) - YouTube channel ID
- `duration_sec` (int, nullable) - Video duration in seconds
- `upload_date` (str, nullable) - Upload date (YYYYMMDD)
- `view_count` (int, nullable) - View count at download time
- `like_count` (int, nullable) - Like count at download time
- `resolution` (str, nullable) - Video resolution
- `file_size_bytes` (int, nullable) - Downloaded file size
- `video_codec` (str, nullable) - Video codec
- `audio_codec` (str, nullable) - Audio codec
- `format_id` (str, nullable) - yt-dlp format ID used
- `transcript_text` (str, nullable) - Full transcript text
- `transcript_source` (str, nullable) - Transcript source
- `subtitle_language` (str, nullable) - Subtitle language code
- `auto_generated` (bool, nullable) - Transcript auto-generated flag
- `download_started_at` (datetime, nullable) - Download start time
- `download_completed_at` (datetime, nullable) - Download completion time
- `error_text` (str, nullable) - Error message if failed

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_video_downloads_request_id ON video_downloads(request_id);
CREATE INDEX idx_video_downloads_video_id ON video_downloads(video_id);
```

**Relationships:**

- One-to-one with `requests`

---

### llm_calls

**Purpose:** OpenRouter LLM API calls for summarization.

**Schema:**

```sql
CREATE TABLE llm_calls (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id               TEXT REFERENCES requests(id),
    provider                 TEXT DEFAULT 'openrouter',
    model                    TEXT NOT NULL,
    endpoint                 TEXT DEFAULT '/api/v1/chat/completions',
    request_headers_json     TEXT,  -- Authorization redacted
    request_messages_json    TEXT,  -- Chat messages array
    request_full_json        TEXT,  -- Full request payload
    response_text            TEXT,  -- Assistant response text
    response_json            TEXT,  -- Full response payload
    prompt_tokens            INTEGER,
    completion_tokens        INTEGER,
    total_tokens             INTEGER,
    cost_usd                 REAL,
    latency_ms               INTEGER,
    status                   TEXT DEFAULT 'ok',  -- 'ok'|'error'
    error_message            TEXT,
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `request_id` (str, FK) - Foreign key to `requests`
- `provider` (str) - LLM provider (`openrouter`)
- `model` (str) - Model name (e.g., `deepseek/deepseek-v3.2`)
- `endpoint` (str) - API endpoint
- `request_headers_json` (str, nullable) - Request headers (Authorization redacted)
- `request_messages_json` (str) - Chat messages array as JSON
- `request_full_json` (str, nullable) - Full request payload
- `response_text` (str, nullable) - Assistant response text
- `response_json` (str, nullable) - Full response payload
- `prompt_tokens` (int, nullable) - Input tokens used
- `completion_tokens` (int, nullable) - Output tokens used
- `total_tokens` (int, nullable) - Total tokens used
- `cost_usd` (float, nullable) - Estimated cost in USD
- `latency_ms` (int, nullable) - API call latency
- `status` (str) - Call status (`ok` or `error`)
- `error_message` (str, nullable) - Error details if failed
- `created_at` (datetime) - Record creation timestamp

**Indexes:**

```sql
CREATE INDEX idx_llm_calls_request_id ON llm_calls(request_id);
CREATE INDEX idx_llm_calls_created_at ON llm_calls(created_at);
CREATE INDEX idx_llm_calls_model ON llm_calls(model);
```

**Relationships:**

- Many-to-one with `requests`

---

### summaries

**Purpose:** Final validated summary JSON sent to user.

**Schema:**

```sql
CREATE TABLE summaries (
    id               TEXT PRIMARY KEY,
    request_id       TEXT UNIQUE REFERENCES requests(id),
    lang             TEXT NOT NULL,  -- 'en', 'ru', etc.
    summary_json     TEXT NOT NULL,  -- Full summary JSON payload
    version          INTEGER DEFAULT 1,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Summary ID
- `request_id` (str, FK, unique) - Foreign key to `requests`
- `lang` (str) - Summary language
- `summary_json` (str) - Full summary JSON (validated against contract)
- `version` (int) - Summary version (increments on regeneration)
- `created_at` (datetime) - Record creation timestamp

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_summaries_request_id ON summaries(request_id);
CREATE INDEX idx_summaries_created_at ON summaries(created_at);
```

**Relationships:**

- One-to-one with `requests`
- One-to-one with `summary_embeddings`

---

## Search and Discovery Tables

### topic_search_index

**Purpose:** SQLite FTS5 full-text search index.

**Schema:**

```sql
CREATE VIRTUAL TABLE topic_search_index USING fts5(
    summary_id UNINDEXED,
    content,
    tokenize = 'porter ascii'
);
```

**Fields:**

- `summary_id` (str) - Foreign key to `summaries.id` (not indexed)
- `content` (str) - Searchable content (key_ideas + topic_tags + entities)

**Relationships:**

- Many-to-one with `summaries` (via `summary_id`)

---

### summary_embeddings

**Purpose:** Vector embeddings for semantic search.

**Schema:**

```sql
CREATE TABLE summary_embeddings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    summary_id        TEXT UNIQUE REFERENCES summaries(id),
    embedding_model   TEXT NOT NULL,  -- 'all-MiniLM-L6-v2', etc.
    embedding_vector  BLOB,  -- Serialized numpy array
    embedding_dim     INTEGER,  -- Vector dimensions (e.g., 384)
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `summary_id` (str, FK, unique) - Foreign key to `summaries`
- `embedding_model` (str) - Model name used for embedding
- `embedding_vector` (blob) - Serialized embedding vector
- `embedding_dim` (int) - Vector dimensions
- `created_at` (datetime) - Record creation timestamp

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_summary_embeddings_summary_id ON summary_embeddings(summary_id);
```

**Relationships:**

- One-to-one with `summaries`

---

## Mobile API Tables

### user_devices

**Purpose:** Track mobile devices for sync.

**Schema:**

```sql
CREATE TABLE user_devices (
    id                 TEXT PRIMARY KEY,
    user_id            INTEGER REFERENCES users(telegram_user_id),
    device_name        TEXT,
    device_type        TEXT,  -- 'ios', 'android', 'web'
    last_sync_token    TEXT,
    last_sync_at       TIMESTAMP,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Device ID (UUID)
- `user_id` (int, FK) - Foreign key to `users`
- `device_name` (str, nullable) - Device name (user-defined)
- `device_type` (str, nullable) - Device type
- `last_sync_token` (str, nullable) - Last sync token
- `last_sync_at` (datetime, nullable) - Last sync timestamp
- `created_at` (datetime) - Record creation timestamp

**Indexes:**

```sql
CREATE INDEX idx_user_devices_user_id ON user_devices(user_id);
```

**Relationships:**

- Many-to-one with `users`

---

### refresh_tokens

**Purpose:** JWT refresh tokens for Mobile API.

**Schema:**

```sql
CREATE TABLE refresh_tokens (
    id              TEXT PRIMARY KEY,
    user_id         INTEGER REFERENCES users(telegram_user_id),
    token_hash      TEXT UNIQUE NOT NULL,
    device_id       TEXT,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked         INTEGER DEFAULT 0,  -- 0/1 boolean
    revoked_at      TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Token ID (UUID)
- `user_id` (int, FK) - Foreign key to `users`
- `token_hash` (str, unique) - SHA256 hash of refresh token
- `device_id` (str, nullable) - Associated device ID
- `expires_at` (datetime) - Token expiration timestamp
- `created_at` (datetime) - Token creation timestamp
- `revoked` (bool) - Revocation flag
- `revoked_at` (datetime, nullable) - Revocation timestamp

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);
CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
```

**Relationships:**

- Many-to-one with `users`

---

### collections

**Purpose:** User-created collections of summaries.

**Schema:**

```sql
CREATE TABLE collections (
    id              TEXT PRIMARY KEY,
    user_id         INTEGER REFERENCES users(telegram_user_id),
    name            TEXT NOT NULL,
    description     TEXT,
    icon            TEXT,
    color           TEXT,
    is_public       INTEGER DEFAULT 0,  -- 0/1 boolean
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Collection ID (UUID)
- `user_id` (int, FK) - Foreign key to `users` (collection owner)
- `name` (str) - Collection name
- `description` (str, nullable) - Collection description
- `icon` (str, nullable) - Icon name/emoji
- `color` (str, nullable) - Color hex code
- `is_public` (bool) - Public visibility flag
- `created_at` (datetime) - Creation timestamp
- `updated_at` (datetime) - Last update timestamp

**Indexes:**

```sql
CREATE INDEX idx_collections_user_id ON collections(user_id);
```

**Relationships:**

- Many-to-one with `users`
- One-to-many with `collection_items`
- One-to-many with `collection_collaborators`

---

### collection_items

**Purpose:** Summaries within collections.

**Schema:**

```sql
CREATE TABLE collection_items (
    id              TEXT PRIMARY KEY,
    collection_id   TEXT REFERENCES collections(id) ON DELETE CASCADE,
    summary_id      TEXT REFERENCES summaries(id) ON DELETE CASCADE,
    position        INTEGER,
    notes           TEXT,
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Item ID (UUID)
- `collection_id` (str, FK) - Foreign key to `collections`
- `summary_id` (str, FK) - Foreign key to `summaries`
- `position` (int, nullable) - Item position in collection
- `notes` (str, nullable) - User notes for this item
- `added_at` (datetime) - Timestamp when added to collection

**Indexes:**

```sql
CREATE INDEX idx_collection_items_collection_id ON collection_items(collection_id);
CREATE INDEX idx_collection_items_summary_id ON collection_items(summary_id);
CREATE UNIQUE INDEX idx_collection_items_unique ON collection_items(collection_id, summary_id);
```

**Relationships:**

- Many-to-one with `collections`
- Many-to-one with `summaries`

---

### collection_collaborators

**Purpose:** Users with access to shared collections.

**Schema:**

```sql
CREATE TABLE collection_collaborators (
    id              TEXT PRIMARY KEY,
    collection_id   TEXT REFERENCES collections(id) ON DELETE CASCADE,
    user_id         INTEGER REFERENCES users(telegram_user_id) ON DELETE CASCADE,
    role            TEXT DEFAULT 'viewer',  -- 'owner'| 'editor' |'viewer'
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Collaborator ID (UUID)
- `collection_id` (str, FK) - Foreign key to `collections`
- `user_id` (int, FK) - Foreign key to `users`
- `role` (str) - Access role
- `added_at` (datetime) - Timestamp when added as collaborator

**Indexes:**

```sql
CREATE INDEX idx_collection_collaborators_collection_id ON collection_collaborators(collection_id);
CREATE INDEX idx_collection_collaborators_user_id ON collection_collaborators(user_id);
CREATE UNIQUE INDEX idx_collection_collaborators_unique ON collection_collaborators(collection_id, user_id);
```

**Relationships:**

- Many-to-one with `collections`
- Many-to-one with `users`

---

### collection_invites

**Purpose:** Invite links for collection sharing.

**Schema:**

```sql
CREATE TABLE collection_invites (
    id              TEXT PRIMARY KEY,
    collection_id   TEXT REFERENCES collections(id) ON DELETE CASCADE,
    invite_code     TEXT UNIQUE NOT NULL,
    role            TEXT DEFAULT 'viewer',
    max_uses        INTEGER,
    uses_count      INTEGER DEFAULT 0,
    expires_at      TIMESTAMP,
    created_by      INTEGER REFERENCES users(telegram_user_id),
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked         INTEGER DEFAULT 0,  -- 0/1 boolean
    revoked_at      TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Invite ID (UUID)
- `collection_id` (str, FK) - Foreign key to `collections`
- `invite_code` (str, unique) - Invite code (short UUID)
- `role` (str) - Role granted to invitees
- `max_uses` (int, nullable) - Maximum uses allowed
- `uses_count` (int) - Current use count
- `expires_at` (datetime, nullable) - Expiration timestamp
- `created_by` (int, FK) - Foreign key to `users` (invite creator)
- `created_at` (datetime) - Creation timestamp
- `revoked` (bool) - Revocation flag
- `revoked_at` (datetime, nullable) - Revocation timestamp

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_collection_invites_invite_code ON collection_invites(invite_code);
CREATE INDEX idx_collection_invites_collection_id ON collection_invites(collection_id);
```

**Relationships:**

- Many-to-one with `collections`
- Many-to-one with `users` (via `created_by`)

---

## Audit and Analytics Tables

### user_interactions

**Purpose:** Track user actions for analytics.

**Schema:**

```sql
CREATE TABLE user_interactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(telegram_user_id),
    interaction_type TEXT NOT NULL,  -- 'request'| 'search' | 'collection_create' |etc.
    metadata_json   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `user_id` (int, FK) - Foreign key to `users`
- `interaction_type` (str) - Type of interaction
- `metadata_json` (str, nullable) - Interaction metadata as JSON
- `created_at` (datetime) - Interaction timestamp

**Indexes:**

```sql
CREATE INDEX idx_user_interactions_user_id ON user_interactions(user_id);
CREATE INDEX idx_user_interactions_created_at ON user_interactions(created_at);
```

**Relationships:**

- Many-to-one with `users`

---

### audit_logs

**Purpose:** System-wide audit trail.

**Schema:**

```sql
CREATE TABLE audit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    level           TEXT NOT NULL,  -- 'info'| 'warning' |'error'
    event           TEXT NOT NULL,
    correlation_id  TEXT,
    user_id         INTEGER,
    details_json    TEXT
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `timestamp` (datetime) - Event timestamp
- `level` (str) - Log level
- `event` (str) - Event description
- `correlation_id` (str, nullable) - Request correlation ID
- `user_id` (int, nullable) - Associated user ID
- `details_json` (str, nullable) - Event details as JSON

**Indexes:**

```sql
CREATE INDEX idx_audit_logs_timestamp ON audit_logs(timestamp);
CREATE INDEX idx_audit_logs_correlation_id ON audit_logs(correlation_id);
CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
```

---

### karakeep_sync

**Purpose:** Track Karakeep bookmark sync state.

**Schema:**

```sql
CREATE TABLE karakeep_sync (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER REFERENCES users(telegram_user_id),
    last_sync_at     TIMESTAMP,
    sync_token       TEXT,
    bookmarks_synced INTEGER DEFAULT 0,
    errors_count     INTEGER DEFAULT 0,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Fields:**

- `id` (int, PK, autoincrement) - Internal ID
- `user_id` (int, FK) - Foreign key to `users`
- `last_sync_at` (datetime, nullable) - Last successful sync timestamp
- `sync_token` (str, nullable) - Sync continuation token
- `bookmarks_synced` (int) - Total bookmarks synced
- `errors_count` (int) - Sync error count
- `created_at` (datetime) - Record creation timestamp

**Indexes:**

```sql
CREATE INDEX idx_karakeep_sync_user_id ON karakeep_sync(user_id);
```

**Relationships:**

- Many-to-one with `users`

---

## Client Secrets (Mobile API)

### client_secrets

**Purpose:** Mobile API client credentials.

**Schema:**

```sql
CREATE TABLE client_secrets (
    id                TEXT PRIMARY KEY,
    client_id         TEXT UNIQUE NOT NULL,
    client_secret_hash TEXT NOT NULL,
    client_name       TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    revoked           INTEGER DEFAULT 0,  -- 0/1 boolean
    revoked_at        TIMESTAMP
);
```

**Fields:**

- `id` (str, PK) - Secret ID (UUID)
- `client_id` (str, unique) - Client identifier
- `client_secret_hash` (str) - SHA256 hash of client secret
- `client_name` (str, nullable) - Client application name
- `created_at` (datetime) - Creation timestamp
- `revoked` (bool) - Revocation flag
- `revoked_at` (datetime, nullable) - Revocation timestamp

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_client_secrets_client_id ON client_secrets(client_id);
```

---

## Entity Relationship Diagram

```mermaid
erDiagram
    users | |--o{ requests : "submits"
    users | |--o{ user_interactions : "performs"
    users | |--o{ user_devices : "owns"
    users | |--o{ refresh_tokens : "has"
    users | |--o{ collections : "creates"
    users | |--o{ collection_collaborators : "collaborates"

    chats | |--o{ requests : "contains"
    chats | |--o{ telegram_messages : "has"

    requests | | -- | | telegram_messages : "has"
    requests | | -- | | crawl_results : "has"
    requests | | -- | | video_downloads : "has"
    requests | |--o{ llm_calls : "triggers"
    requests | | -- | | summaries : "produces"

    summaries | | -- | | summary_embeddings : "has"
    summaries | | -- | | topic_search_index : "indexed_in"
    summaries | |--o{ collection_items : "included_in"

    collections | |--o{ collection_items : "contains"
    collections | |--o{ collection_collaborators : "shared_with"
    collections | |--o{ collection_invites : "has"
```

---

## Common Queries

### Find All Summaries for a User

```sql
SELECT s.*
FROM summaries s
JOIN requests r ON s.request_id = r.id
WHERE r.user_id = 123456789
ORDER BY s.created_at DESC
LIMIT 10;
```

### Find Correlation ID from Telegram Message ID

```sql
SELECT r.id as correlation_id
FROM requests r
JOIN telegram_messages tm ON r.id = tm.request_id
WHERE tm.message_id = 12345;
```

### Calculate Total Token Usage by Model

```sql
SELECT
    model,
    COUNT(*) as calls,
    SUM(total_tokens) as total_tokens,
    AVG(total_tokens) as avg_tokens,
    SUM(cost_usd) as total_cost_usd
FROM llm_calls
WHERE created_at > datetime('now', '-30 days')
GROUP BY model
ORDER BY total_tokens DESC;
```

### Find Slow Requests

```sql
SELECT
    r.id,
    r.input_url,
    r.total_processing_time_sec
FROM requests r
WHERE r.total_processing_time_sec > 15
ORDER BY r.total_processing_time_sec DESC
LIMIT 10;
```

---

## Database Maintenance

### Vacuum (Reclaim Space)

```bash
sqlite3 data/app.db "VACUUM;"
```

### Analyze (Update Query Planner Statistics)

```bash
sqlite3 data/app.db "ANALYZE;"
```

### Integrity Check

```bash
sqlite3 data/app.db "PRAGMA integrity_check;"
# Expected output: ok
```

---

## See Also

- [SPEC.md § Data Model](../SPEC.md#data-model-sqlite) - Canonical specification
- [CLI Commands § Database Migration](cli-commands.md#database-migration) - Migration tool
- [How to Backup and Restore](../how-to/backup-and-restore.md) - Backup procedures

---

**Last Updated:** 2026-02-09

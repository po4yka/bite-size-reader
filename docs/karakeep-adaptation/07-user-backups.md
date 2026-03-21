# User-Level Backups

**Status:** Partial (system-level SQLite backup only)
**Complexity:** Small
**Dependencies:** None

## Problem Statement

BSR has system-level SQLite backups via a background loop (configurable interval and retention). There is no per-user self-service backup -- users cannot export all their data as a portable archive or restore from a previous state. Karakeep provides user-initiated backups with scheduling and retention.

## Current State

System backup (documented in `docs/how-to/backup-and-restore.md`):

- Periodic SQLite `.backup()` copies
- Configurable via `BACKUP_INTERVAL_MINUTES` and `BACKUP_RETENTION_DAYS`
- System-level only -- no user-facing API or UI

## Design Goals

- Users can trigger a manual backup of their data
- Backup creates a portable ZIP archive (JSON files + metadata)
- Optional scheduled automatic backups (daily/weekly)
- Download and restore via API
- Retention policy (auto-delete old backups)

## Data Model

New models in `app/db/models.py`:

```python
class UserBackup(BaseModel):
    """Per-user backup archive."""
    id = peewee.AutoField()
    user = peewee.ForeignKeyField(User, backref="backups", on_delete="CASCADE")
    type = peewee.TextField(default="manual")    # manual | scheduled
    status = peewee.TextField(default="pending")  # pending | processing | completed | failed
    file_path = peewee.TextField(null=True)       # relative path in data dir
    file_size_bytes = peewee.IntegerField(null=True)
    items_count = peewee.IntegerField(null=True)  # total records backed up
    error = peewee.TextField(null=True)
    server_version = peewee.BigIntegerField(default=_next_server_version)
    updated_at = peewee.DateTimeField(default=_utcnow)
    created_at = peewee.DateTimeField(default=_utcnow)

    class Meta:
        table_name = "user_backups"
        indexes = (
            (("user",), False),
            (("status",), False),
        )
```

Backup scheduling is stored in user preferences (`preferences_json`):

```json
{
    "backup_enabled": true,
    "backup_frequency": "weekly",
    "backup_retention_count": 5
}
```

## Backup Archive Format

ZIP file named `bsr-backup-{user_id}-{timestamp}.zip`:

```
bsr-backup-123456789-20260321.zip
  manifest.json          # backup metadata
  summaries.json         # all user summaries with full JSON payloads
  requests.json          # all user requests (metadata only, no crawl results)
  tags.json              # all user tags
  summary_tags.json      # tag associations
  collections.json       # collection hierarchy
  collection_items.json  # collection contents
  highlights.json        # all highlights
  preferences.json       # user preferences
```

### manifest.json

```json
{
    "version": 1,
    "app_version": "1.0.0",
    "user_id": 123456789,
    "created_at": "2026-03-21T10:30:00Z",
    "items": {
        "summaries": 342,
        "requests": 380,
        "tags": 25,
        "collections": 8,
        "highlights": 156
    }
}
```

## Backup Pipeline

### Create Backup

```
1. User triggers backup (API or scheduled)
2. Create UserBackup record (status="processing")
3. Background task (APScheduler):
   a. Query all user data (summaries, tags, collections, highlights, preferences)
   b. Serialize to JSON files
   c. Create ZIP archive in data directory
   d. Update UserBackup with file_path, file_size_bytes, items_count
   e. Set status="completed"
4. On error: set status="failed", store error message
```

### Restore from Backup

```
1. User uploads backup ZIP via API
2. Validate manifest.json (version, user_id match)
3. Parse JSON files
4. For each entity type:
   a. Check for conflicts (existing data)
   b. Import new records, skip duplicates (by dedupe_hash for requests)
   c. Restore tag associations, collection memberships, highlights
5. Return restore summary (created/skipped/errors)
```

### Scheduled Backups

- APScheduler job checks daily for users with `backup_enabled=true`
- If `backup_frequency` matches (daily/weekly based on last backup date):
  - Trigger backup
  - After completion, enforce `backup_retention_count` (delete oldest backups)

## API Endpoints

New router or extend `app/api/routers/user.py`:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/backups` | Trigger manual backup. Rate limit: 3 per hour. |
| `GET` | `/v1/backups` | List user's backups |
| `GET` | `/v1/backups/{id}` | Get backup details |
| `GET` | `/v1/backups/{id}/download` | Download backup ZIP (streaming response) |
| `DELETE` | `/v1/backups/{id}` | Delete backup (removes file) |
| `POST` | `/v1/backups/restore` | Upload and restore from backup ZIP |
| `PATCH` | `/v1/backups/schedule` | Update backup schedule preferences |
| `GET` | `/v1/backups/schedule` | Get current backup schedule |

### Backup Response

```json
{
    "id": 7,
    "type": "manual",
    "status": "completed",
    "file_size_bytes": 2457600,
    "items_count": 342,
    "created_at": "2026-03-21T10:30:00Z"
}
```

### Restore Response

```json
{
    "status": "completed",
    "restored": {
        "summaries": 342,
        "tags": 25,
        "collections": 8,
        "highlights": 156
    },
    "skipped": {
        "summaries": 15
    },
    "errors": []
}
```

## Frontend (React + Carbon)

### New Components

- **BackupsPage** (`web/src/features/backups/BackupsPage.tsx`) -- two sections:
  - **Backups list**: Carbon `DataTable` with status, size, date, download/delete actions
  - **Schedule**: backup frequency toggle (Carbon `Toggle`), frequency selector, retention count
- **BackupProgress** (`web/src/features/backups/BackupProgress.tsx`) -- in-progress indicator with status polling
- **RestoreUpload** (`web/src/features/backups/RestoreUpload.tsx`) -- Carbon `FileUploader` for restore, with results summary

### Route

Add `/web/backups` route under settings/preferences section.

## Telegram Bot Integration

- `/backup` -- trigger manual backup. Bot responds with progress and sends ZIP as file attachment when complete.
- `/backups` -- list recent backups with download links (deep links to web UI)

## Storage Management

### File Location

Backups stored in `{DATA_DIR}/backups/{user_id}/` directory.

### Cleanup

- Scheduled cleanup removes backups beyond retention count
- On user deletion: cascade removes all backup files
- Max backup size: warn if backup exceeds 500MB (log warning, don't block)

## Security

- Backups contain user data -- must be access-controlled
- Download endpoint validates `user_id` matches authenticated user
- Restore validates `user_id` in manifest matches authenticated user
- Backup files are not publicly accessible (served via API only)

## Testing

- Unit test: verify ZIP structure and manifest format
- Integration test: trigger backup, download, verify contents match DB
- Restore test: create backup, delete data, restore, verify data recovered
- Schedule test: verify APScheduler creates backups on schedule
- Retention test: verify old backups are deleted after retention count exceeded
- Rate limit test: verify 3/hour limit on manual backups
